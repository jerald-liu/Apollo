{
	"patcher" : {
		"fileversion" : 1,
		"appversion" : {
			"major" : 8,
			"minor" : 6,
			"revision" : 4,
			"architecture" : "x64",
			"modernui" : 1
		},
		"classnamespace" : "dsp.midifx",
		"rect" : [ 0, 0, 900, 750 ],
		"bglocked" : 0,
		"openinpresentation" : 1,
		"defaultlockeddisplayoptions" : 1,
		"gridonopen" : 1,
		"gridsnaponopen" : 1,
		"gridsize" : [ 8.0, 8.0 ],
		"boxes" : [
			{
				"box" : {
					"id" : "obj-midiin",
					"maxclass" : "midiin",
					"patching_rect" : [ 24, 48, 55, 22 ],
					"numinlets" : 1,
					"numoutlets" : 1
				}
			},
			{
				"box" : {
					"id" : "obj-midiparse",
					"maxclass" : "midiparse",
					"patching_rect" : [ 24, 96, 78, 22 ],
					"numinlets" : 1,
					"numoutlets" : 8
				}
			},
			{
				"box" : {
					"id" : "obj-midiformat-passthrough",
					"maxclass" : "midiformat",
					"patching_rect" : [ 144, 96, 78, 22 ],
					"numinlets" : 7,
					"numoutlets" : 1
				}
			},
			{
				"box" : {
					"id" : "obj-midiout",
					"maxclass" : "midiout",
					"patching_rect" : [ 144, 144, 55, 22 ],
					"numinlets" : 1,
					"numoutlets" : 0
				}
			},
			{
				"box" : {
					"id" : "obj-input-activity-trigger",
					"maxclass" : "newobj",
					"text" : "t b l",
					"patching_rect" : [ 24, 144, 40, 22 ],
					"numinlets" : 1,
					"numoutlets" : 2
				}
			},
			{
				"box" : {
					"id" : "obj-input-hit-msg",
					"maxclass" : "message",
					"text" : "input_hit",
					"patching_rect" : [ 24, 192, 65, 22 ],
					"numinlets" : 2,
					"numoutlets" : 1
				}
			},
			{
				"box" : {
					"id" : "obj-note-parser",
					"maxclass" : "newobj",
					"text" : "p note_to_osc",
					"patching_rect" : [ 96, 144, 110, 22 ],
					"numinlets" : 1,
					"numoutlets" : 1,
					"patcher" : {
						"fileversion" : 1,
						"appversion" : {
							"major" : 8,
							"minor" : 6,
							"revision" : 4,
							"architecture" : "x64",
							"modernui" : 1
						},
						"rect" : [ 0, 0, 400, 320 ],
						"bglocked" : 0,
						"boxes" : [
							{
								"box" : {
									"id" : "sub-inlet",
									"maxclass" : "inlet",
									"patching_rect" : [ 180, 24, 30, 30 ],
									"numinlets" : 0,
									"numoutlets" : 1,
									"comment" : "note list [pitch vel] from midiparse"
								}
							},
							{
								"box" : {
									"id" : "sub-unpack",
									"maxclass" : "newobj",
									"text" : "unpack 0 0",
									"patching_rect" : [ 160, 88, 80, 22 ],
									"numinlets" : 1,
									"numoutlets" : 2
								}
							},
							{
								"box" : {
									"id" : "sub-pak",
									"maxclass" : "newobj",
									"text" : "pak 0 0 100. 300. 0",
									"patching_rect" : [ 100, 160, 160, 22 ],
									"numinlets" : 5,
									"numoutlets" : 1
								}
							},
							{
								"box" : {
									"id" : "sub-prepend",
									"maxclass" : "newobj",
									"text" : "prepend note",
									"patching_rect" : [ 100, 210, 100, 22 ],
									"numinlets" : 2,
									"numoutlets" : 1
								}
							},
							{
								"box" : {
									"id" : "sub-outlet",
									"maxclass" : "outlet",
									"patching_rect" : [ 100, 268, 30, 30 ],
									"numinlets" : 1,
									"numoutlets" : 0,
									"comment" : "note pitch vel ioi_ms dur_ms pedal"
								}
							}
						],
						"lines" : [
							{ "patchline" : { "source" : [ "sub-inlet", 0 ], "destination" : [ "sub-unpack", 0 ] } },
							{ "patchline" : { "source" : [ "sub-unpack", 0 ], "destination" : [ "sub-pak", 0 ] } },
							{ "patchline" : { "source" : [ "sub-unpack", 1 ], "destination" : [ "sub-pak", 1 ] } },
							{ "patchline" : { "source" : [ "sub-pak", 0 ], "destination" : [ "sub-prepend", 0 ] } },
							{ "patchline" : { "source" : [ "sub-prepend", 0 ], "destination" : [ "sub-outlet", 0 ] } }
						]
					}
				}
			},
			{
				"box" : {
					"id" : "obj-node",
					"maxclass" : "newobj",
					"text" : "node.script apollo_bridge.js",
					"patching_rect" : [ 96, 216, 200, 22 ],
					"numinlets" : 1,
					"numoutlets" : 2
				}
			},
			{
				"box" : {
					"id" : "obj-route-node",
					"maxclass" : "newobj",
					"text" : "route gen_note gen_cc gen_timbre status connection latency",
					"patching_rect" : [ 96, 264, 340, 22 ],
					"numinlets" : 1,
					"numoutlets" : 7
				}
			},
			{
				"box" : {
					"id" : "obj-unpack-note",
					"maxclass" : "newobj",
					"text" : "unpack i i f f i",
					"patching_rect" : [ 96, 312, 120, 22 ],
					"numinlets" : 1,
					"numoutlets" : 5
				}
			},
			{
				"box" : {
					"id" : "obj-output-hit-msg",
					"maxclass" : "message",
					"text" : "output_hit",
					"patching_rect" : [ 96, 360, 70, 22 ],
					"numinlets" : 2,
					"numoutlets" : 1
				}
			},
			{
				"box" : {
					"id" : "obj-delay-note",
					"maxclass" : "newobj",
					"text" : "pipe 0 0 0",
					"patching_rect" : [ 96, 408, 80, 22 ],
					"numinlets" : 4,
					"numoutlets" : 3
				}
			},
			{
				"box" : {
					"id" : "obj-gate-mute",
					"maxclass" : "gate",
					"patching_rect" : [ 96, 456, 44, 22 ],
					"numinlets" : 2,
					"numoutlets" : 1
				}
			},
			{
				"box" : {
					"id" : "obj-mute-toggle",
					"maxclass" : "newobj",
					"text" : "!- 1",
					"patching_rect" : [ 160, 432, 40, 22 ],
					"numinlets" : 2,
					"numoutlets" : 1
				}
			},
			{
				"box" : {
					"id" : "obj-makenote",
					"maxclass" : "newobj",
					"text" : "makenote 100 500",
					"patching_rect" : [ 96, 504, 120, 22 ],
					"numinlets" : 3,
					"numoutlets" : 2
				}
			},
			{
				"box" : {
					"id" : "obj-noteout",
					"maxclass" : "noteout",
					"patching_rect" : [ 96, 552, 55, 22 ],
					"numinlets" : 3,
					"numoutlets" : 0
				}
			},
			{
				"box" : {
					"id" : "obj-unpack-cc",
					"maxclass" : "newobj",
					"text" : "unpack i i",
					"patching_rect" : [ 256, 312, 72, 22 ],
					"numinlets" : 1,
					"numoutlets" : 2
				}
			},
			{
				"box" : {
					"id" : "obj-ctlout",
					"maxclass" : "ctlout",
					"patching_rect" : [ 256, 360, 44, 22 ],
					"numinlets" : 3,
					"numoutlets" : 0
				}
			},
			{
				"box" : {
					"id" : "obj-timbre-msg-prefix",
					"maxclass" : "newobj",
					"text" : "prepend timbre",
					"patching_rect" : [ 360, 312, 110, 22 ],
					"numinlets" : 1,
					"numoutlets" : 1
				}
			},
			{
				"box" : {
					"id" : "obj-jsui-status",
					"maxclass" : "jsui",
					"patching_rect" : [ 490, 48, 72, 56 ],
					"presentation" : 1,
					"presentation_rect" : [ 366, 8, 72, 56 ],
					"scriptname" : "apollo_status.js",
					"numinlets" : 1,
					"numoutlets" : 1
				}
			},
			{
				"box" : {
					"id" : "obj-jsui-activity",
					"maxclass" : "jsui",
					"patching_rect" : [ 490, 120, 56, 80 ],
					"presentation" : 1,
					"presentation_rect" : [ 444, 8, 56, 80 ],
					"scriptname" : "apollo_activity.js",
					"numinlets" : 1,
					"numoutlets" : 1
				}
			},
			{
				"box" : {
					"id" : "obj-jsui-timbre",
					"maxclass" : "jsui",
					"patching_rect" : [ 360, 360, 120, 90 ],
					"presentation" : 1,
					"presentation_rect" : [ 366, 72, 134, 90 ],
					"scriptname" : "apollo_timbre_meters.js",
					"numinlets" : 1,
					"numoutlets" : 1
				}
			},
			{
				"box" : {
					"id" : "obj-engine-toggle",
					"maxclass" : "live.toggle",
					"patching_rect" : [ 496, 216, 24, 24 ],
					"presentation" : 1,
					"presentation_rect" : [ 8, 8, 24, 24 ],
					"parameter_enable" : 1,
					"varname" : "engine[1]",
					"Parameter" : {
						"parameter_longname" : "Engine",
						"parameter_shortname" : "Eng",
						"parameter_initial" : [ 0 ],
						"parameter_type" : 2
					},
					"numinlets" : 1,
					"numoutlets" : 1
				}
			},
			{
				"box" : {
					"id" : "obj-engine-sel",
					"maxclass" : "newobj",
					"text" : "sel 0 1",
					"patching_rect" : [ 496, 264, 55, 22 ],
					"numinlets" : 1,
					"numoutlets" : 3
				}
			},
			{
				"box" : {
					"id" : "obj-engine-stop-msg",
					"maxclass" : "message",
					"text" : "engine_stop",
					"patching_rect" : [ 496, 312, 80, 22 ],
					"numinlets" : 2,
					"numoutlets" : 1
				}
			},
			{
				"box" : {
					"id" : "obj-engine-start-msg",
					"maxclass" : "message",
					"text" : "engine_start",
					"patching_rect" : [ 592, 312, 85, 22 ],
					"numinlets" : 2,
					"numoutlets" : 1
				}
			},
			{
				"box" : {
					"id" : "obj-model-menu",
					"maxclass" : "live.menu",
					"patching_rect" : [ 496, 360, 120, 24 ],
					"presentation" : 1,
					"presentation_rect" : [ 40, 8, 120, 24 ],
					"parameter_enable" : 1,
					"varname" : "model[1]",
					"items" : "base, large",
					"Parameter" : {
						"parameter_longname" : "Model",
						"parameter_shortname" : "Model",
						"parameter_initial" : [ 0 ],
						"parameter_type" : 1,
						"parameter_steps" : 2
					},
					"numinlets" : 1,
					"numoutlets" : 3
				}
			},
			{
				"box" : {
					"id" : "obj-model-sel",
					"maxclass" : "newobj",
					"text" : "sel 0 1",
					"patching_rect" : [ 496, 408, 55, 22 ],
					"numinlets" : 1,
					"numoutlets" : 3
				}
			},
			{
				"box" : {
					"id" : "obj-model-base-msg",
					"maxclass" : "message",
					"text" : "model_load base",
					"patching_rect" : [ 496, 456, 110, 22 ],
					"numinlets" : 2,
					"numoutlets" : 1
				}
			},
			{
				"box" : {
					"id" : "obj-model-large-msg",
					"maxclass" : "message",
					"text" : "model_load large",
					"patching_rect" : [ 624, 456, 115, 22 ],
					"numinlets" : 2,
					"numoutlets" : 1
				}
			},
			{
				"box" : {
					"id" : "obj-temperature",
					"maxclass" : "live.dial",
					"patching_rect" : [ 496, 504, 40, 48 ],
					"presentation" : 1,
					"presentation_rect" : [ 8, 44, 40, 48 ],
					"parameter_enable" : 1,
					"varname" : "temperature[1]",
					"Parameter" : {
						"parameter_longname" : "Temperature",
						"parameter_shortname" : "Temp",
						"parameter_initial" : [ 0.9 ],
						"parameter_minimum" : 0.5,
						"parameter_maximum" : 1.5,
						"parameter_steps" : 100,
						"parameter_type" : 0,
						"parameter_unitstyle" : 0,
						"parameter_annotation" : "Sampling temperature — higher = more random"
					},
					"numinlets" : 1,
					"numoutlets" : 2
				}
			},
			{
				"box" : {
					"id" : "obj-topk",
					"maxclass" : "live.dial",
					"patching_rect" : [ 552, 504, 40, 48 ],
					"presentation" : 1,
					"presentation_rect" : [ 56, 44, 40, 48 ],
					"parameter_enable" : 1,
					"varname" : "topk[1]",
					"Parameter" : {
						"parameter_longname" : "Top-K",
						"parameter_shortname" : "TopK",
						"parameter_initial" : [ 50 ],
						"parameter_minimum" : 5,
						"parameter_maximum" : 100,
						"parameter_steps" : 95,
						"parameter_type" : 1,
						"parameter_annotation" : "Top-K sampling — limits vocabulary to K most likely tokens"
					},
					"numinlets" : 1,
					"numoutlets" : 2
				}
			},
			{
				"box" : {
					"id" : "obj-density",
					"maxclass" : "live.dial",
					"patching_rect" : [ 608, 504, 40, 48 ],
					"presentation" : 1,
					"presentation_rect" : [ 104, 44, 40, 48 ],
					"parameter_enable" : 1,
					"varname" : "density[1]",
					"Parameter" : {
						"parameter_longname" : "Density",
						"parameter_shortname" : "Dens",
						"parameter_initial" : [ 0.5 ],
						"parameter_minimum" : 0.0,
						"parameter_maximum" : 1.0,
						"parameter_steps" : 100,
						"parameter_type" : 0,
						"parameter_annotation" : "Note density — how many notes Apollo generates per phrase"
					},
					"numinlets" : 1,
					"numoutlets" : 2
				}
			},
			{
				"box" : {
					"id" : "obj-timbre-inf",
					"maxclass" : "live.dial",
					"patching_rect" : [ 664, 504, 40, 48 ],
					"presentation" : 1,
					"presentation_rect" : [ 152, 44, 40, 48 ],
					"parameter_enable" : 1,
					"varname" : "timbre_influence[1]",
					"Parameter" : {
						"parameter_longname" : "Timbre Influence",
						"parameter_shortname" : "Timb",
						"parameter_initial" : [ 0.7 ],
						"parameter_minimum" : 0.0,
						"parameter_maximum" : 1.0,
						"parameter_steps" : 100,
						"parameter_type" : 0,
						"parameter_annotation" : "How strongly timbral predictions influence CC outputs"
					},
					"numinlets" : 1,
					"numoutlets" : 2
				}
			},
			{
				"box" : {
					"id" : "obj-config-pack",
					"maxclass" : "newobj",
					"text" : "pack config 0.9 50 0.5 0.7",
					"patching_rect" : [ 496, 568, 200, 22 ],
					"numinlets" : 5,
					"numoutlets" : 1
				}
			},
			{
				"box" : {
					"id" : "obj-bright-offset",
					"maxclass" : "live.dial",
					"patching_rect" : [ 496, 600, 40, 48 ],
					"presentation" : 1,
					"presentation_rect" : [ 8, 104, 40, 48 ],
					"parameter_enable" : 1,
					"varname" : "bright_offset[1]",
					"Parameter" : {
						"parameter_longname" : "Brightness Offset",
						"parameter_shortname" : "B Off",
						"parameter_initial" : [ 0.0 ],
						"parameter_minimum" : -0.5,
						"parameter_maximum" : 0.5,
						"parameter_steps" : 100,
						"parameter_type" : 0,
						"parameter_annotation" : "Shift all brightness predictions up or down"
					},
					"numinlets" : 1,
					"numoutlets" : 2
				}
			},
			{
				"box" : {
					"id" : "obj-attack-offset",
					"maxclass" : "live.dial",
					"patching_rect" : [ 552, 600, 40, 48 ],
					"presentation" : 1,
					"presentation_rect" : [ 56, 104, 40, 48 ],
					"parameter_enable" : 1,
					"varname" : "attack_offset[1]",
					"Parameter" : {
						"parameter_longname" : "Attack Offset",
						"parameter_shortname" : "A Off",
						"parameter_initial" : [ 0.0 ],
						"parameter_minimum" : -0.5,
						"parameter_maximum" : 0.5,
						"parameter_steps" : 100,
						"parameter_type" : 0,
						"parameter_annotation" : "Shift all attack predictions up or down"
					},
					"numinlets" : 1,
					"numoutlets" : 2
				}
			},
			{
				"box" : {
					"id" : "obj-rich-offset",
					"maxclass" : "live.dial",
					"patching_rect" : [ 608, 600, 40, 48 ],
					"presentation" : 1,
					"presentation_rect" : [ 104, 104, 40, 48 ],
					"parameter_enable" : 1,
					"varname" : "rich_offset[1]",
					"Parameter" : {
						"parameter_longname" : "Richness Offset",
						"parameter_shortname" : "R Off",
						"parameter_initial" : [ 0.0 ],
						"parameter_minimum" : -0.5,
						"parameter_maximum" : 0.5,
						"parameter_steps" : 100,
						"parameter_type" : 0,
						"parameter_annotation" : "Shift all richness predictions up or down"
					},
					"numinlets" : 1,
					"numoutlets" : 2
				}
			},
			{
				"box" : {
					"id" : "obj-timbre-offset-pack",
					"maxclass" : "newobj",
					"text" : "pack timbre_offset 0. 0. 0.",
					"patching_rect" : [ 496, 664, 170, 22 ],
					"numinlets" : 4,
					"numoutlets" : 1
				}
			},
			{
				"box" : {
					"id" : "obj-cc-bright",
					"maxclass" : "live.numbox",
					"patching_rect" : [ 496, 696, 50, 24 ],
					"presentation" : 1,
					"presentation_rect" : [ 200, 104, 50, 24 ],
					"parameter_enable" : 1,
					"varname" : "cc_bright[1]",
					"Parameter" : {
						"parameter_longname" : "Brightness CC",
						"parameter_shortname" : "B CC",
						"parameter_initial" : [ 74 ],
						"parameter_minimum" : 0,
						"parameter_maximum" : 127,
						"parameter_steps" : 128,
						"parameter_type" : 1,
						"parameter_annotation" : "MIDI CC# for brightness (default CC74 Filter Cutoff)"
					},
					"numinlets" : 1,
					"numoutlets" : 2
				}
			},
			{
				"box" : {
					"id" : "obj-cc-attack",
					"maxclass" : "live.numbox",
					"patching_rect" : [ 554, 696, 50, 24 ],
					"presentation" : 1,
					"presentation_rect" : [ 256, 104, 50, 24 ],
					"parameter_enable" : 1,
					"varname" : "cc_attack[1]",
					"Parameter" : {
						"parameter_longname" : "Attack CC",
						"parameter_shortname" : "A CC",
						"parameter_initial" : [ 73 ],
						"parameter_minimum" : 0,
						"parameter_maximum" : 127,
						"parameter_steps" : 128,
						"parameter_type" : 1,
						"parameter_annotation" : "MIDI CC# for attack (default CC73 Attack Time)"
					},
					"numinlets" : 1,
					"numoutlets" : 2
				}
			},
			{
				"box" : {
					"id" : "obj-cc-rich",
					"maxclass" : "live.numbox",
					"patching_rect" : [ 612, 696, 50, 24 ],
					"presentation" : 1,
					"presentation_rect" : [ 312, 104, 50, 24 ],
					"parameter_enable" : 1,
					"varname" : "cc_rich[1]",
					"Parameter" : {
						"parameter_longname" : "Richness CC",
						"parameter_shortname" : "R CC",
						"parameter_initial" : [ 71 ],
						"parameter_minimum" : 0,
						"parameter_maximum" : 127,
						"parameter_steps" : 128,
						"parameter_type" : 1,
						"parameter_annotation" : "MIDI CC# for richness (default CC71 Resonance)"
					},
					"numinlets" : 1,
					"numoutlets" : 2
				}
			},
			{
				"box" : {
					"id" : "obj-cc-map-pack",
					"maxclass" : "newobj",
					"text" : "pack cc_map 74 73 71",
					"patching_rect" : [ 496, 728, 160, 22 ],
					"numinlets" : 4,
					"numoutlets" : 1
				}
			},
			{
				"box" : {
					"id" : "obj-vel-scale",
					"maxclass" : "live.dial",
					"patching_rect" : [ 720, 504, 40, 48 ],
					"presentation" : 1,
					"presentation_rect" : [ 200, 44, 40, 48 ],
					"parameter_enable" : 1,
					"varname" : "vel_scale[1]",
					"Parameter" : {
						"parameter_longname" : "Velocity Scale",
						"parameter_shortname" : "Vel",
						"parameter_initial" : [ 1.0 ],
						"parameter_minimum" : 0.0,
						"parameter_maximum" : 2.0,
						"parameter_steps" : 200,
						"parameter_type" : 0,
						"parameter_annotation" : "Scale generated note velocities"
					},
					"numinlets" : 1,
					"numoutlets" : 2
				}
			},
			{
				"box" : {
					"id" : "obj-vel-scale-msg",
					"maxclass" : "message",
					"text" : "velocity_scale $1",
					"patching_rect" : [ 720, 568, 110, 22 ],
					"numinlets" : 2,
					"numoutlets" : 1
				}
			},
			{
				"box" : {
					"id" : "obj-mute",
					"maxclass" : "live.toggle",
					"patching_rect" : [ 720, 600, 24, 24 ],
					"presentation" : 1,
					"presentation_rect" : [ 248, 44, 24, 24 ],
					"parameter_enable" : 1,
					"varname" : "mute[1]",
					"Parameter" : {
						"parameter_longname" : "Mute",
						"parameter_shortname" : "Mute",
						"parameter_initial" : [ 0 ],
						"parameter_type" : 2
					},
					"numinlets" : 1,
					"numoutlets" : 1
				}
			},
			{
				"box" : {
					"id" : "obj-bypass",
					"maxclass" : "live.toggle",
					"patching_rect" : [ 760, 600, 24, 24 ],
					"presentation" : 1,
					"presentation_rect" : [ 280, 44, 24, 24 ],
					"parameter_enable" : 1,
					"varname" : "bypass[1]",
					"Parameter" : {
						"parameter_longname" : "Bypass",
						"parameter_shortname" : "Byp",
						"parameter_initial" : [ 0 ],
						"parameter_type" : 2
					},
					"numinlets" : 1,
					"numoutlets" : 1
				}
			},
			{
				"box" : {
					"id" : "obj-bypass-msg",
					"maxclass" : "message",
					"text" : "bypass $1",
					"patching_rect" : [ 760, 640, 80, 22 ],
					"numinlets" : 2,
					"numoutlets" : 1
				}
			},
			{
				"box" : {
					"id" : "obj-comment-mute",
					"maxclass" : "comment",
					"text" : "Mute",
					"patching_rect" : [ 718, 628, 40, 20 ],
					"presentation" : 1,
					"presentation_rect" : [ 246, 70, 40, 20 ],
					"fontsize" : 9.0
				}
			},
			{
				"box" : {
					"id" : "obj-comment-bypass",
					"maxclass" : "comment",
					"text" : "Bypass",
					"patching_rect" : [ 756, 628, 48, 20 ],
					"presentation" : 1,
					"presentation_rect" : [ 278, 70, 48, 20 ],
					"fontsize" : 9.0
				}
			},
			{
				"box" : {
					"id" : "obj-cc-label",
					"maxclass" : "comment",
					"text" : "CC#",
					"patching_rect" : [ 496, 676, 40, 20 ],
					"presentation" : 1,
					"presentation_rect" : [ 200, 88, 40, 20 ],
					"fontsize" : 9.0
				}
			},
			{
				"box" : {
					"id" : "obj-comment-title",
					"maxclass" : "comment",
					"text" : "APOLLO",
					"patching_rect" : [ 24, 16, 80, 20 ],
					"presentation" : 1,
					"presentation_rect" : [ 168, 8, 80, 20 ],
					"fontname" : "Arial Bold",
					"fontsize" : 13.0,
					"frgb" : [ 0.8, 0.8, 0.8, 1.0 ]
				}
			},
			{
				"box" : {
					"id" : "obj-comment-version",
					"maxclass" : "comment",
					"text" : "v0.4.1",
					"patching_rect" : [ 110, 16, 56, 20 ],
					"presentation" : 1,
					"presentation_rect" : [ 250, 12, 56, 20 ],
					"fontsize" : 9.0,
					"frgb" : [ 0.5, 0.5, 0.5, 1.0 ]
				}
			},
			{
				"box" : {
					"id" : "obj-latency-display",
					"maxclass" : "live.numbox",
					"patching_rect" : [ 490, 112, 56, 24 ],
					"presentation" : 1,
					"presentation_rect" : [ 314, 44, 48, 24 ],
					"parameter_enable" : 0,
					"Parameter" : {
						"parameter_longname" : "Latency ms",
						"parameter_shortname" : "ms",
						"parameter_initial" : [ 0 ],
						"parameter_minimum" : 0,
						"parameter_maximum" : 999,
						"parameter_type" : 0
					},
					"numinlets" : 1,
					"numoutlets" : 2
				}
			},
			{
				"box" : {
					"id" : "obj-comment-latency",
					"maxclass" : "comment",
					"text" : "ms",
					"patching_rect" : [ 490, 138, 40, 20 ],
					"presentation" : 1,
					"presentation_rect" : [ 314, 70, 40, 20 ],
					"fontsize" : 9.0,
					"frgb" : [ 0.5, 0.5, 0.5, 1.0 ]
				}
			},
			{
				"box" : {
					"id" : "obj-loadbang",
					"maxclass" : "newobj",
					"text" : "loadbang",
					"patching_rect" : [ 24, 600, 60, 22 ],
					"numinlets" : 1,
					"numoutlets" : 1
				}
			}
		],
		"lines" : [
			{ "patchline" : { "source" : [ "obj-midiin", 0 ], "destination" : [ "obj-midiparse", 0 ] } },
			{ "patchline" : { "source" : [ "obj-midiparse", 0 ], "destination" : [ "obj-input-activity-trigger", 0 ] } },
			{ "patchline" : { "source" : [ "obj-midiparse", 2 ], "destination" : [ "obj-midiformat-passthrough", 2 ] } },
			{ "patchline" : { "source" : [ "obj-midiformat-passthrough", 0 ], "destination" : [ "obj-midiout", 0 ] } },
			{ "patchline" : { "source" : [ "obj-input-activity-trigger", 0 ], "destination" : [ "obj-input-hit-msg", 0 ] } },
			{ "patchline" : { "source" : [ "obj-input-activity-trigger", 1 ], "destination" : [ "obj-note-parser", 0 ] } },
			{ "patchline" : { "source" : [ "obj-input-hit-msg", 0 ], "destination" : [ "obj-jsui-activity", 0 ] } },
			{ "patchline" : { "source" : [ "obj-note-parser", 0 ], "destination" : [ "obj-node", 0 ] } },
			{ "patchline" : { "source" : [ "obj-node", 0 ], "destination" : [ "obj-route-node", 0 ] } },
			{ "patchline" : { "source" : [ "obj-route-node", 0 ], "destination" : [ "obj-unpack-note", 0 ] } },
			{ "patchline" : { "source" : [ "obj-route-node", 1 ], "destination" : [ "obj-unpack-cc", 0 ] } },
			{ "patchline" : { "source" : [ "obj-route-node", 2 ], "destination" : [ "obj-timbre-msg-prefix", 0 ] } },
			{ "patchline" : { "source" : [ "obj-route-node", 3 ], "destination" : [ "obj-jsui-status", 0 ] } },
			{ "patchline" : { "source" : [ "obj-route-node", 4 ], "destination" : [ "obj-jsui-status", 0 ] } },
			{ "patchline" : { "source" : [ "obj-route-node", 5 ], "destination" : [ "obj-latency-display", 0 ] } },
			{ "patchline" : { "source" : [ "obj-timbre-msg-prefix", 0 ], "destination" : [ "obj-jsui-timbre", 0 ] } },
			{ "patchline" : { "source" : [ "obj-unpack-note", 0 ], "destination" : [ "obj-delay-note", 0 ] } },
			{ "patchline" : { "source" : [ "obj-unpack-note", 0 ], "destination" : [ "obj-output-hit-msg", 0 ] } },
			{ "patchline" : { "source" : [ "obj-unpack-note", 1 ], "destination" : [ "obj-delay-note", 1 ] } },
			{ "patchline" : { "source" : [ "obj-unpack-note", 2 ], "destination" : [ "obj-delay-note", 3 ] } },
			{ "patchline" : { "source" : [ "obj-unpack-note", 3 ], "destination" : [ "obj-makenote", 2 ] } },
			{ "patchline" : { "source" : [ "obj-output-hit-msg", 0 ], "destination" : [ "obj-jsui-activity", 0 ] } },
			{ "patchline" : { "source" : [ "obj-delay-note", 0 ], "destination" : [ "obj-gate-mute", 1 ] } },
			{ "patchline" : { "source" : [ "obj-delay-note", 1 ], "destination" : [ "obj-makenote", 1 ] } },
			{ "patchline" : { "source" : [ "obj-mute", 0 ], "destination" : [ "obj-mute-toggle", 0 ] } },
			{ "patchline" : { "source" : [ "obj-mute-toggle", 0 ], "destination" : [ "obj-gate-mute", 0 ] } },
			{ "patchline" : { "source" : [ "obj-gate-mute", 0 ], "destination" : [ "obj-makenote", 0 ] } },
			{ "patchline" : { "source" : [ "obj-makenote", 0 ], "destination" : [ "obj-noteout", 0 ] } },
			{ "patchline" : { "source" : [ "obj-makenote", 1 ], "destination" : [ "obj-noteout", 1 ] } },
			{ "patchline" : { "source" : [ "obj-unpack-cc", 0 ], "destination" : [ "obj-ctlout", 1 ] } },
			{ "patchline" : { "source" : [ "obj-unpack-cc", 1 ], "destination" : [ "obj-ctlout", 0 ] } },
			{ "patchline" : { "source" : [ "obj-engine-toggle", 0 ], "destination" : [ "obj-engine-sel", 0 ] } },
			{ "patchline" : { "source" : [ "obj-engine-sel", 0 ], "destination" : [ "obj-engine-stop-msg", 0 ] } },
			{ "patchline" : { "source" : [ "obj-engine-sel", 1 ], "destination" : [ "obj-engine-start-msg", 0 ] } },
			{ "patchline" : { "source" : [ "obj-engine-stop-msg", 0 ], "destination" : [ "obj-node", 0 ] } },
			{ "patchline" : { "source" : [ "obj-engine-start-msg", 0 ], "destination" : [ "obj-node", 0 ] } },
			{ "patchline" : { "source" : [ "obj-model-menu", 0 ], "destination" : [ "obj-model-sel", 0 ] } },
			{ "patchline" : { "source" : [ "obj-model-sel", 0 ], "destination" : [ "obj-model-base-msg", 0 ] } },
			{ "patchline" : { "source" : [ "obj-model-sel", 1 ], "destination" : [ "obj-model-large-msg", 0 ] } },
			{ "patchline" : { "source" : [ "obj-model-base-msg", 0 ], "destination" : [ "obj-node", 0 ] } },
			{ "patchline" : { "source" : [ "obj-model-large-msg", 0 ], "destination" : [ "obj-node", 0 ] } },
			{ "patchline" : { "source" : [ "obj-temperature", 0 ], "destination" : [ "obj-config-pack", 1 ] } },
			{ "patchline" : { "source" : [ "obj-topk", 0 ], "destination" : [ "obj-config-pack", 2 ] } },
			{ "patchline" : { "source" : [ "obj-density", 0 ], "destination" : [ "obj-config-pack", 3 ] } },
			{ "patchline" : { "source" : [ "obj-timbre-inf", 0 ], "destination" : [ "obj-config-pack", 4 ] } },
			{ "patchline" : { "source" : [ "obj-config-pack", 0 ], "destination" : [ "obj-node", 0 ] } },
			{ "patchline" : { "source" : [ "obj-bright-offset", 0 ], "destination" : [ "obj-timbre-offset-pack", 1 ] } },
			{ "patchline" : { "source" : [ "obj-attack-offset", 0 ], "destination" : [ "obj-timbre-offset-pack", 2 ] } },
			{ "patchline" : { "source" : [ "obj-rich-offset", 0 ], "destination" : [ "obj-timbre-offset-pack", 3 ] } },
			{ "patchline" : { "source" : [ "obj-timbre-offset-pack", 0 ], "destination" : [ "obj-node", 0 ] } },
			{ "patchline" : { "source" : [ "obj-cc-bright", 0 ], "destination" : [ "obj-cc-map-pack", 1 ] } },
			{ "patchline" : { "source" : [ "obj-cc-attack", 0 ], "destination" : [ "obj-cc-map-pack", 2 ] } },
			{ "patchline" : { "source" : [ "obj-cc-rich", 0 ], "destination" : [ "obj-cc-map-pack", 3 ] } },
			{ "patchline" : { "source" : [ "obj-cc-map-pack", 0 ], "destination" : [ "obj-node", 0 ] } },
			{ "patchline" : { "source" : [ "obj-vel-scale", 0 ], "destination" : [ "obj-vel-scale-msg", 0 ] } },
			{ "patchline" : { "source" : [ "obj-vel-scale-msg", 0 ], "destination" : [ "obj-node", 0 ] } },
			{ "patchline" : { "source" : [ "obj-bypass", 0 ], "destination" : [ "obj-bypass-msg", 0 ] } },
			{ "patchline" : { "source" : [ "obj-bypass-msg", 0 ], "destination" : [ "obj-node", 0 ] } },
			{ "patchline" : { "source" : [ "obj-loadbang", 0 ], "destination" : [ "obj-jsui-status", 0 ] } },
			{ "patchline" : { "source" : [ "obj-loadbang", 0 ], "destination" : [ "obj-jsui-timbre", 0 ] } },
			{ "patchline" : { "source" : [ "obj-loadbang", 0 ], "destination" : [ "obj-jsui-activity", 0 ] } }
		],
		"parameters" : {
			"parameter_overrides" : [
				{ "parameter_path" : "engine[1]" },
				{ "parameter_path" : "model[1]" },
				{ "parameter_path" : "temperature[1]" },
				{ "parameter_path" : "topk[1]" },
				{ "parameter_path" : "density[1]" },
				{ "parameter_path" : "timbre_influence[1]" },
				{ "parameter_path" : "bright_offset[1]" },
				{ "parameter_path" : "attack_offset[1]" },
				{ "parameter_path" : "rich_offset[1]" },
				{ "parameter_path" : "cc_bright[1]" },
				{ "parameter_path" : "cc_attack[1]" },
				{ "parameter_path" : "cc_rich[1]" },
				{ "parameter_path" : "vel_scale[1]" },
				{ "parameter_path" : "mute[1]" },
				{ "parameter_path" : "bypass[1]" }
			],
			"inherited_shortform" : 0
		}
	}
}
