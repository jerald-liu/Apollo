"""Background training job state holder (APP-01, D-02, D-03, D-07).

TrainingJob wraps a subprocess.Popen call to `python -m apollo.scripts.train`
and reads its stdout lines in a daemon thread to update live training state.

Design notes:
- DO NOT use communicate() -- it blocks until subprocess exits, destroying
  the real-time progress effect (RESEARCH Pitfall 2).
- bufsize=1 + text=True enables line-by-line iteration without pipe deadlock.
- A threading.Lock guards all state fields read by the /status polling endpoint.
"""
from __future__ import annotations

import re
import subprocess
import threading


class TrainingJob:
    """Holds state for one background training subprocess.

    Status transitions: idle -> running -> (complete | error)
    Re-starting resets to running; prior history is cleared.
    """

    def __init__(self) -> None:
        self.status: str = "idle"          # idle | running | complete | error
        self.epoch: int = 0
        self.total_epochs: int = 0
        self.train_loss: float | None = None
        self.held_loss: float | None = None
        self.loss_history: list[dict] = []  # [{epoch, train_loss, held_loss}]
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._on_complete = None  # set by start(); called after subprocess exits 0

    def start(
        self,
        pairs_root: str,
        epochs: int,
        output_dir: str,
        on_complete=None,
    ) -> bool:
        """Launch training subprocess in a daemon thread.

        Parameters
        ----------
        pairs_root:
            Path to the corpus pairs directory (passed to train.py argv).
        epochs:
            Number of training epochs.
        output_dir:
            Directory where train.py writes the checkpoint (passed to argv).
        on_complete:
            Optional callable invoked after the subprocess exits with code 0.
            Signature: ``on_complete(train_loss: float | None, held_loss: float | None)``.
            Exceptions raised inside ``on_complete`` are caught and logged to
            stderr — a registry-append failure must NOT crash the training
            thread (APP-14 completion-hook requirement).

        Returns False (no-op) if already running; otherwise True.
        """
        with self._lock:
            if self.status == "running":
                return False
            self.status = "running"
            self.epoch = 0
            self.total_epochs = epochs
            self.train_loss = None
            self.held_loss = None
            self.loss_history = []

        self._on_complete = on_complete

        cmd = [
            "python", "-m", "apollo.scripts.train",
            pairs_root,
            "--epochs", str(epochs),
            "--output-dir", output_dir,
        ]
        self._proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,  # line-buffered — avoids deadlock on 64 KB pipe fill
        )
        t = threading.Thread(target=self._read_stdout, daemon=True)
        t.start()
        return True

    def _read_stdout(self) -> None:
        """Drain subprocess stdout and parse epoch/loss lines.

        train.py stdout format (VERIFIED apollo/scripts/train.py line 174):
            epoch {E}/{N}  train_loss={X:.4f}  held_loss={Y:.4f}
        """
        assert self._proc is not None
        pattern = re.compile(r"epoch (\d+)/(\d+)\s+train_loss=([\d.]+)\s+held_loss=([\d.nan]+)")
        for line in self._proc.stdout:  # type: ignore[union-attr]
            m = pattern.search(line)
            if m:
                with self._lock:
                    self.epoch = int(m.group(1))
                    self.total_epochs = int(m.group(2))
                    self.train_loss = float(m.group(3))
                    try:
                        self.held_loss = float(m.group(4))
                    except ValueError:
                        self.held_loss = None
                    self.loss_history.append({
                        "epoch": self.epoch,
                        "train_loss": self.train_loss,
                        "held_loss": self.held_loss,
                    })
        ret = self._proc.wait()
        with self._lock:
            self.status = "complete" if ret == 0 else "error"

        # Invoke the completion callback (APP-14 registry hook).
        # Only called on clean exit (ret == 0).  Exceptions are swallowed so a
        # registry-append failure never crashes the training daemon thread.
        if ret == 0 and self._on_complete is not None:
            try:
                self._on_complete(self.train_loss, self.held_loss)
            except Exception as exc:
                import sys
                print(f"[TrainingJob] on_complete raised: {exc!r}", file=sys.stderr)

    def snapshot(self) -> dict:
        """Return a thread-safe snapshot of current job state."""
        with self._lock:
            return {
                "status": self.status,
                "epoch": self.epoch,
                "total_epochs": self.total_epochs,
                "train_loss": self.train_loss,
                "held_loss": self.held_loss,
                "loss_history": list(self.loss_history),
            }
