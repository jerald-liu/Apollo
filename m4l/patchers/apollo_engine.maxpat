{
	"patcher" : {
		"fileversion" : 1,
		"appversion" : {
			"major" : 8,
			"minor" : 6,
			"revision" : 0,
			"architecture" : "x64",
			"modernui" : 1
		},
		"classnamespace" : "box",
		"rect" : [ 100, 100, 900, 600 ],
		"bglocked" : 0,
		"openinpresentation" : 1,
		"default_fontsize" : 10.0,
		"default_fontname" : "Ableton Sans Medium",
		"gridonopen" : 1,
		"gridsize" : [ 15.0, 15.0 ],
		"gridsnaponopen" : 1,
		"objectsnaponopen" : 1,
		"statusbarvisible" : 2,
		"toolbarvisible" : 0,
		"devicewidth" : 670.0,
		"description" : "Apollo AI Jamming Companion — generates expressive musical responses with timbral control",
		"digest" : "AI-powered real-time musical response generator",
		"tags" : "MIDI Effect, AI, Generative, Apollo",
		"style" : "",
		"boxes" : [

			{
				"box" : {
					"id" : "obj-midiin",
					"maxclass" : "midiin",
					"numinlets" : 1,
					"numoutlets" : 1,
					"outlettype" : [ "int" ],
					"patching_rect" : [ 30.0, 30.0, 50.0, 20.0 ]
				}
			},
			{
				"box" : {
					"id" : "obj-midiparse",
					"maxclass" : "midiparse",
					"numinlets" : 1,
					"numoutlets" : 8,
					"outlettype" : [ "", "", "", "int", "int", "", "int", "" ],
					"patching_rect" : [ 30.0, 60.0, 200.0, 20.0 ]
				}
			},
			{
				"box" : {
					"id" : "obj-midiout",
					"maxclass" : "midiout",
					"numinlets" : 1,
					"numoutlets" : 0,
					"patching_rect" : [ 30.0, 530.0, 50.0, 20.0 ]
				}
			},
			{
				"box" : {
					"id" : "obj-midiformat-passthrough",
					"maxclass" : "midiformat",
					"numinlets" : 7,
					"numoutlets" : 1,
					"outlettype" : [ "int" ],
					"patching_rect" : [ 30.0, 500.0, 200.0, 20.0 ]
				}
			},

			{
				"box" : {
					"id" : "obj-note-parser",
					"maxclass" : "newobj",
					"text" : "p note_to_osc",
					"numinlets" : 1,
					"numoutlets" : 1,
					"outlettype" : [ "" ],
					"patching_rect" : [ 30.0, 150.0, 80.0, 20.0 ],
					"patcher" : {
						"fileversion" : 1,
						"appversion" : { "major" : 8, "minor" : 6, "revision" : 0, "architecture" : "x64", "modernui" : 1 },
						"classnamespace" : "box",
						"rect" : [ 0, 0, 400, 300 ],
						"boxes" : [
							{ "box" : { "id" : "obj-inlet", "maxclass" : "inlet", "numinlets" : 0, "numoutlets" : 1, "outlettype" : [ "" ], "patching_rect" : [ 30.0, 20.0, 30.0, 30.0 ] } },
							{ "box" : { "id" : "obj-unpack-midi", "maxclass" : "newobj", "text" : "unpack i i", "numinlets" : 1, "numoutlets" : 2, "outlettype" : [ "int", "int" ], "patching_rect" : [ 30.0, 60.0, 60.0, 20.0 ] } },
							{ "box" : { "id" : "obj-velocity-norm", "maxclass" : "newobj", "text" : "/ 127.", "numinlets" : 2, "numoutlets" : 1, "outlettype" : [ "float" ], "patching_rect" : [ 100.0, 90.0, 40.0, 20.0 ] } },
							{ "box" : { "id" : "obj-timer", "maxclass" : "newobj", "text" : "timer", "numinlets" : 2, "numoutlets" : 1, "outlettype" : [ "float" ], "patching_rect" : [ 170.0, 90.0, 45.0, 20.0 ] } },
							{ "box" : { "id" : "obj-delta-to-sec", "maxclass" : "newobj", "text" : "/ 1000.", "numinlets" : 2, "numoutlets" : 1, "outlettype" : [ "float" ], "patching_rect" : [ 170.0, 120.0, 50.0, 20.0 ] } },
							{ "box" : { "id" : "obj-pack-osc", "maxclass" : "newobj", "text" : "pack note i f f 0.5 0", "numinlets" : 6, "numoutlets" : 1, "outlettype" : [ "" ], "patching_rect" : [ 30.0, 160.0, 180.0, 20.0 ] } },
							{ "box" : { "id" : "obj-outlet", "maxclass" : "outlet", "numinlets" : 1, "numoutlets" : 0, "patching_rect" : [ 30.0, 200.0, 30.0, 30.0 ] } }
						],
						"lines" : [
							{ "patchline" : { "source" : [ "obj-inlet", 0 ], "destination" : [ "obj-unpack-midi", 0 ] } },
							{ "patchline" : { "source" : [ "obj-unpack-midi", 0 ], "destination" : [ "obj-pack-osc", 1 ] } },
							{ "patchline" : { "source" : [ "obj-unpack-midi", 0 ], "destination" : [ "obj-timer", 0 ] } },
							{ "patchline" : { "source" : [ "obj-unpack-midi", 1 ], "destination" : [ "obj-velocity-norm", 0 ] } },
							{ "patchline" : { "source" : [ "obj-velocity-norm", 0 ], "destination" : [ "obj-pack-osc", 2 ] } },
							{ "patchline" : { "source" : [ "obj-timer", 0 ], "destination" : [ "obj-delta-to-sec", 0 ] } },
							{ "patchline" : { "source" : [ "obj-delta-to-sec", 0 ], "destination" : [ "obj-pack-osc", 3 ] } },
							{ "patchline" : { "source" : [ "obj-pack-osc", 0 ], "destination" : [ "obj-outlet", 0 ] } }
						]
					}
				}
			},

			{
				"box" : {
					"id" : "obj-input-activity-trigger",
					"maxclass" : "newobj",
					"text" : "t b l",
					"numinlets" : 1,
					"numoutlets" : 2,
					"outlettype" : [ "bang", "" ],
					"patching_rect" : [ 30.0, 100.0, 60.0, 20.0 ],
					"comment" : "Trigger input activity meter + forward note"
				}
			},
			{
				"box" : {
					"id" : "obj-input-hit-msg",
					"maxclass" : "message",
					"text" : "input_hit",
					"numinlets" : 2,
					"numoutlets" : 1,
					"outlettype" : [ "" ],
					"patching_rect" : [ 30.0, 125.0, 55.0, 20.0 ]
				}
			},

			{
				"box" : {
					"id" : "obj-node",
					"maxclass" : "newobj",
					"text" : "node.script apollo_bridge.js",
					"numinlets" : 1,
					"numoutlets" : 2,
					"outlettype" : [ "", "" ],
					"patching_rect" : [ 300.0, 240.0, 180.0, 20.0 ]
				}
			},
			{
				"box" : {
					"id" : "obj-route-node",
					"maxclass" : "newobj",
					"text" : "route gen_note gen_cc gen_timbre status connection latency error",
					"numinlets" : 1,
					"numoutlets" : 8,
					"outlettype" : [ "", "", "", "", "", "", "", "" ],
					"patching_rect" : [ 300.0, 280.0, 380.0, 20.0 ]
				}
			},

			{
				"box" : {
					"id" : "obj-unpack-note",
					"maxclass" : "newobj",
					"text" : "unpack i i f f i",
					"numinlets" : 1,
					"numoutlets" : 5,
					"outlettype" : [ "int", "int", "float", "float", "int" ],
					"patching_rect" : [ 300.0, 320.0, 150.0, 20.0 ]
				}
			},
			{
				"box" : {
					"id" : "obj-output-hit-msg",
					"maxclass" : "message",
					"text" : "output_hit",
					"numinlets" : 2,
					"numoutlets" : 1,
					"outlettype" : [ "" ],
					"patching_rect" : [ 300.0, 345.0, 60.0, 20.0 ]
				}
			},
			{
				"box" : {
					"id" : "obj-delay-note",
					"maxclass" : "newobj",
					"text" : "pipe 0 0 0",
					"numinlets" : 4,
					"numoutlets" : 3,
					"outlettype" : [ "int", "int", "" ],
					"patching_rect" : [ 300.0, 380.0, 100.0, 20.0 ]
				}
			},
			{
				"box" : {
					"id" : "obj-gate-mute",
					"maxclass" : "gate",
					"numinlets" : 2,
					"numoutlets" : 1,
					"outlettype" : [ "" ],
					"patching_rect" : [ 300.0, 410.0, 40.0, 20.0 ]
				}
			},
			{
				"box" : {
					"id" : "obj-mute-toggle",
					"maxclass" : "newobj",
					"text" : "!- 1",
					"numinlets" : 2,
					"numoutlets" : 1,
					"outlettype" : [ "int" ],
					"patching_rect" : [ 260.0, 410.0, 30.0, 20.0 ]
				}
			},
			{
				"box" : {
					"id" : "obj-makenote",
					"maxclass" : "newobj",
					"text" : "makenote 100 500",
					"numinlets" : 3,
					"numoutlets" : 2,
					"outlettype" : [ "float", "float" ],
					"patching_rect" : [ 300.0, 440.0, 100.0, 20.0 ]
				}
			},
			{
				"box" : {
					"id" : "obj-noteout",
					"maxclass" : "noteout",
					"numinlets" : 3,
					"numoutlets" : 0,
					"patching_rect" : [ 300.0, 470.0, 80.0, 20.0 ]
				}
			},
			{
				"box" : {
					"id" : "obj-unpack-cc",
					"maxclass" : "newobj",
					"text" : "unpack i i",
					"numinlets" : 1,
					"numoutlets" : 2,
					"outlettype" : [ "int", "int" ],
					"patching_rect" : [ 470.0, 440.0, 60.0, 20.0 ]
				}
			},
			{
				"box" : {
					"id" : "obj-ctlout",
					"maxclass" : "ctlout",
					"numinlets" : 3,
					"numoutlets" : 0,
					"patching_rect" : [ 470.0, 470.0, 80.0, 20.0 ]
				}
			},

			{
				"box" : {
					"id" : "obj-jsui-status",
					"maxclass" : "jsui",
					"numinlets" : 1,
					"numoutlets" : 1,
					"outlettype" : [ "" ],
					"patching_rect" : [ 700.0, 30.0, 60.0, 50.0 ],
					"filename" : "apollo_status.js",
					"presentation" : 1,
					"presentation_rect" : [ 5.0, 5.0, 60.0, 50.0 ]
				}
			},
			{
				"box" : {
					"id" : "obj-engine-toggle",
					"maxclass" : "live.toggle",
					"varname" : "engine_toggle",
					"numinlets" : 1,
					"numoutlets" : 1,
					"outlettype" : [ "" ],
					"parameter_enable" : 1,
					"patching_rect" : [ 700.0, 100.0, 20.0, 20.0 ],
					"presentation" : 1,
					"presentation_rect" : [ 20.0, 60.0, 30.0, 16.0 ],
					"saved_attribute_attributes" : {
						"valueof" : {
							"parameter_longname" : "Engine",
							"parameter_shortname" : "Engine",
							"parameter_type" : 2,
							"parameter_mmax" : 1.0,
							"parameter_enum" : [ "Off", "On" ]
						}
					}
				}
			},
			{
				"box" : {
					"id" : "obj-engine-sel",
					"maxclass" : "newobj",
					"text" : "sel 0 1",
					"numinlets" : 1,
					"numoutlets" : 3,
					"outlettype" : [ "bang", "bang", "" ],
					"patching_rect" : [ 700.0, 130.0, 60.0, 20.0 ]
				}
			},
			{
				"box" : {
					"id" : "obj-engine-stop-msg",
					"maxclass" : "message",
					"text" : "engine_stop",
					"numinlets" : 2,
					"numoutlets" : 1,
					"outlettype" : [ "" ],
					"patching_rect" : [ 700.0, 160.0, 70.0, 20.0 ]
				}
			},
			{
				"box" : {
					"id" : "obj-engine-start-msg",
					"maxclass" : "message",
					"text" : "engine_start",
					"numinlets" : 2,
					"numoutlets" : 1,
					"outlettype" : [ "" ],
					"patching_rect" : [ 780.0, 160.0, 75.0, 20.0 ]
				}
			},

			{
				"box" : {
					"id" : "obj-model-menu",
					"maxclass" : "live.menu",
					"varname" : "model_select",
					"numinlets" : 1,
					"numoutlets" : 3,
					"outlettype" : [ "", "", "float" ],
					"parameter_enable" : 1,
					"patching_rect" : [ 700.0, 200.0, 80.0, 16.0 ],
					"presentation" : 1,
					"presentation_rect" : [ 5.0, 80.0, 60.0, 16.0 ],
					"saved_attribute_attributes" : {
						"valueof" : {
							"parameter_longname" : "Model",
							"parameter_shortname" : "Model",
							"parameter_type" : 2,
							"parameter_enum" : [ "Base", "Large" ]
						}
					}
				}
			},
			{
				"box" : {
					"id" : "obj-model-sel",
					"maxclass" : "newobj",
					"text" : "sel 0 1",
					"numinlets" : 1,
					"numoutlets" : 3,
					"outlettype" : [ "bang", "bang", "" ],
					"patching_rect" : [ 700.0, 225.0, 60.0, 20.0 ]
				}
			},
			{
				"box" : {
					"id" : "obj-model-base-msg",
					"maxclass" : "message",
					"text" : "model_load base",
					"numinlets" : 2,
					"numoutlets" : 1,
					"outlettype" : [ "" ],
					"patching_rect" : [ 700.0, 250.0, 90.0, 20.0 ]
				}
			},
			{
				"box" : {
					"id" : "obj-model-large-msg",
					"maxclass" : "message",
					"text" : "model_load large",
					"numinlets" : 2,
					"numoutlets" : 1,
					"outlettype" : [ "" ],
					"patching_rect" : [ 790.0, 250.0, 95.0, 20.0 ]
				}
			},

			{
				"box" : {
					"id" : "obj-temperature",
					"maxclass" : "live.dial",
					"varname" : "temperature",
					"numinlets" : 1,
					"numoutlets" : 2,
					"outlettype" : [ "", "float" ],
					"parameter_enable" : 1,
					"patching_rect" : [ 120.0, 200.0, 44.0, 48.0 ],
					"presentation" : 1,
					"presentation_rect" : [ 80.0, 5.0, 44.0, 48.0 ],
					"saved_attribute_attributes" : {
						"valueof" : {
							"parameter_longname" : "Temp",
							"parameter_shortname" : "Temp",
							"parameter_type" : 0,
							"parameter_unitstyle" : 1,
							"parameter_mmin" : 0.0,
							"parameter_mmax" : 2.0,
							"parameter_initial" : [ 0.9 ],
							"parameter_initial_enable" : 1
						}
					}
				}
			},
			{
				"box" : {
					"id" : "obj-topk",
					"maxclass" : "live.dial",
					"varname" : "topk",
					"numinlets" : 1,
					"numoutlets" : 2,
					"outlettype" : [ "", "float" ],
					"parameter_enable" : 1,
					"patching_rect" : [ 170.0, 200.0, 44.0, 48.0 ],
					"presentation" : 1,
					"presentation_rect" : [ 125.0, 5.0, 44.0, 48.0 ],
					"saved_attribute_attributes" : {
						"valueof" : {
							"parameter_longname" : "Top-K",
							"parameter_shortname" : "Top-K",
							"parameter_type" : 1,
							"parameter_unitstyle" : 0,
							"parameter_mmin" : 1.0,
							"parameter_mmax" : 100.0,
							"parameter_initial" : [ 50 ],
							"parameter_initial_enable" : 1
						}
					}
				}
			},
			{
				"box" : {
					"id" : "obj-density",
					"maxclass" : "live.dial",
					"varname" : "density",
					"numinlets" : 1,
					"numoutlets" : 2,
					"outlettype" : [ "", "float" ],
					"parameter_enable" : 1,
					"patching_rect" : [ 120.0, 260.0, 44.0, 48.0 ],
					"presentation" : 1,
					"presentation_rect" : [ 80.0, 52.0, 44.0, 48.0 ],
					"saved_attribute_attributes" : {
						"valueof" : {
							"parameter_longname" : "Density",
							"parameter_shortname" : "Density",
							"parameter_type" : 0,
							"parameter_unitstyle" : 1,
							"parameter_mmin" : 0.0,
							"parameter_mmax" : 1.0,
							"parameter_initial" : [ 0.5 ],
							"parameter_initial_enable" : 1
						}
					}
				}
			},
			{
				"box" : {
					"id" : "obj-timbre-inf",
					"maxclass" : "live.dial",
					"varname" : "timbre_influence",
					"numinlets" : 1,
					"numoutlets" : 2,
					"outlettype" : [ "", "float" ],
					"parameter_enable" : 1,
					"patching_rect" : [ 170.0, 260.0, 44.0, 48.0 ],
					"presentation" : 1,
					"presentation_rect" : [ 125.0, 52.0, 44.0, 48.0 ],
					"saved_attribute_attributes" : {
						"valueof" : {
							"parameter_longname" : "Timbre",
							"parameter_shortname" : "Timbre",
							"parameter_type" : 0,
							"parameter_unitstyle" : 1,
							"parameter_mmin" : 0.0,
							"parameter_mmax" : 1.0,
							"parameter_initial" : [ 0.7 ],
							"parameter_initial_enable" : 1
						}
					}
				}
			},

			{
				"box" : {
					"id" : "obj-config-pack",
					"maxclass" : "newobj",
					"text" : "pack config 0.9 50 0.5 0.7",
					"numinlets" : 5,
					"numoutlets" : 1,
					"outlettype" : [ "" ],
					"patching_rect" : [ 120.0, 330.0, 160.0, 20.0 ]
				}
			},

			{
				"box" : {
					"id" : "obj-bright-offset",
					"maxclass" : "live.dial",
					"varname" : "bright_offset",
					"numinlets" : 1,
					"numoutlets" : 2,
					"outlettype" : [ "", "float" ],
					"parameter_enable" : 1,
					"patching_rect" : [ 300.0, 30.0, 44.0, 48.0 ],
					"presentation" : 1,
					"presentation_rect" : [ 185.0, 5.0, 44.0, 48.0 ],
					"saved_attribute_attributes" : {
						"valueof" : {
							"parameter_longname" : "Bright",
							"parameter_shortname" : "Bright",
							"parameter_type" : 0,
							"parameter_unitstyle" : 1,
							"parameter_mmin" : -1.0,
							"parameter_mmax" : 1.0,
							"parameter_initial" : [ 0.0 ],
							"parameter_initial_enable" : 1
						}
					}
				}
			},
			{
				"box" : {
					"id" : "obj-attack-offset",
					"maxclass" : "live.dial",
					"varname" : "attack_offset",
					"numinlets" : 1,
					"numoutlets" : 2,
					"outlettype" : [ "", "float" ],
					"parameter_enable" : 1,
					"patching_rect" : [ 350.0, 30.0, 44.0, 48.0 ],
					"presentation" : 1,
					"presentation_rect" : [ 230.0, 5.0, 44.0, 48.0 ],
					"saved_attribute_attributes" : {
						"valueof" : {
							"parameter_longname" : "Attack",
							"parameter_shortname" : "Attack",
							"parameter_type" : 0,
							"parameter_unitstyle" : 1,
							"parameter_mmin" : -1.0,
							"parameter_mmax" : 1.0,
							"parameter_initial" : [ 0.0 ],
							"parameter_initial_enable" : 1
						}
					}
				}
			},
			{
				"box" : {
					"id" : "obj-rich-offset",
					"maxclass" : "live.dial",
					"varname" : "rich_offset",
					"numinlets" : 1,
					"numoutlets" : 2,
					"outlettype" : [ "", "float" ],
					"parameter_enable" : 1,
					"patching_rect" : [ 400.0, 30.0, 44.0, 48.0 ],
					"presentation" : 1,
					"presentation_rect" : [ 275.0, 5.0, 44.0, 48.0 ],
					"saved_attribute_attributes" : {
						"valueof" : {
							"parameter_longname" : "Rich",
							"parameter_shortname" : "Rich",
							"parameter_type" : 0,
							"parameter_unitstyle" : 1,
							"parameter_mmin" : -1.0,
							"parameter_mmax" : 1.0,
							"parameter_initial" : [ 0.0 ],
							"parameter_initial_enable" : 1
						}
					}
				}
			},

			{
				"box" : {
					"id" : "obj-timbre-offset-pack",
					"maxclass" : "newobj",
					"text" : "pack timbre_offset 0. 0. 0.",
					"numinlets" : 4,
					"numoutlets" : 1,
					"outlettype" : [ "" ],
					"patching_rect" : [ 300.0, 100.0, 160.0, 20.0 ]
				}
			},

			{
				"box" : {
					"id" : "obj-cc-bright",
					"maxclass" : "live.numbox",
					"varname" : "cc_bright",
					"numinlets" : 1,
					"numoutlets" : 2,
					"outlettype" : [ "", "float" ],
					"parameter_enable" : 1,
					"patching_rect" : [ 300.0, 130.0, 36.0, 16.0 ],
					"presentation" : 1,
					"presentation_rect" : [ 192.0, 54.0, 30.0, 16.0 ],
					"saved_attribute_attributes" : {
						"valueof" : {
							"parameter_longname" : "CC B",
							"parameter_shortname" : "CC B",
							"parameter_type" : 1,
							"parameter_unitstyle" : 0,
							"parameter_mmin" : 0.0,
							"parameter_mmax" : 127.0,
							"parameter_initial" : [ 74 ],
							"parameter_initial_enable" : 1
						}
					}
				}
			},
			{
				"box" : {
					"id" : "obj-cc-attack",
					"maxclass" : "live.numbox",
					"varname" : "cc_attack",
					"numinlets" : 1,
					"numoutlets" : 2,
					"outlettype" : [ "", "float" ],
					"parameter_enable" : 1,
					"patching_rect" : [ 350.0, 130.0, 36.0, 16.0 ],
					"presentation" : 1,
					"presentation_rect" : [ 237.0, 54.0, 30.0, 16.0 ],
					"saved_attribute_attributes" : {
						"valueof" : {
							"parameter_longname" : "CC A",
							"parameter_shortname" : "CC A",
							"parameter_type" : 1,
							"parameter_unitstyle" : 0,
							"parameter_mmin" : 0.0,
							"parameter_mmax" : 127.0,
							"parameter_initial" : [ 73 ],
							"parameter_initial_enable" : 1
						}
					}
				}
			},
			{
				"box" : {
					"id" : "obj-cc-rich",
					"maxclass" : "live.numbox",
					"varname" : "cc_rich",
					"numinlets" : 1,
					"numoutlets" : 2,
					"outlettype" : [ "", "float" ],
					"parameter_enable" : 1,
					"patching_rect" : [ 400.0, 130.0, 36.0, 16.0 ],
					"presentation" : 1,
					"presentation_rect" : [ 282.0, 54.0, 30.0, 16.0 ],
					"saved_attribute_attributes" : {
						"valueof" : {
							"parameter_longname" : "CC R",
							"parameter_shortname" : "CC R",
							"parameter_type" : 1,
							"parameter_unitstyle" : 0,
							"parameter_mmin" : 0.0,
							"parameter_mmax" : 127.0,
							"parameter_initial" : [ 71 ],
							"parameter_initial_enable" : 1
						}
					}
				}
			},
			{
				"box" : {
					"id" : "obj-cc-map-pack",
					"maxclass" : "newobj",
					"text" : "pack cc_map 74 73 71",
					"numinlets" : 4,
					"numoutlets" : 1,
					"outlettype" : [ "" ],
					"patching_rect" : [ 300.0, 160.0, 130.0, 20.0 ]
				}
			},
			{
				"box" : {
					"id" : "obj-cc-label",
					"maxclass" : "comment",
					"text" : "CC#",
					"numinlets" : 1,
					"numoutlets" : 0,
					"presentation" : 1,
					"presentation_rect" : [ 185.0, 71.0, 25.0, 16.0 ],
					"patching_rect" : [ 300.0, 115.0, 25.0, 18.0 ],
					"fontsize" : 8.0,
					"textcolor" : [ 0.5, 0.5, 0.5, 1.0 ]
				}
			},

			{
				"box" : {
					"id" : "obj-vel-scale",
					"maxclass" : "live.dial",
					"varname" : "vel_scale",
					"numinlets" : 1,
					"numoutlets" : 2,
					"outlettype" : [ "", "float" ],
					"parameter_enable" : 1,
					"patching_rect" : [ 500.0, 30.0, 44.0, 48.0 ],
					"presentation" : 1,
					"presentation_rect" : [ 330.0, 5.0, 44.0, 48.0 ],
					"saved_attribute_attributes" : {
						"valueof" : {
							"parameter_longname" : "Vel",
							"parameter_shortname" : "Vel",
							"parameter_type" : 0,
							"parameter_unitstyle" : 1,
							"parameter_mmin" : 0.5,
							"parameter_mmax" : 1.5,
							"parameter_initial" : [ 1.0 ],
							"parameter_initial_enable" : 1
						}
					}
				}
			},
			{
				"box" : {
					"id" : "obj-vel-scale-msg",
					"maxclass" : "message",
					"text" : "velocity_scale $1",
					"numinlets" : 2,
					"numoutlets" : 1,
					"outlettype" : [ "" ],
					"patching_rect" : [ 500.0, 90.0, 100.0, 20.0 ]
				}
			},
			{
				"box" : {
					"id" : "obj-mute",
					"maxclass" : "live.toggle",
					"varname" : "mute",
					"numinlets" : 1,
					"numoutlets" : 1,
					"outlettype" : [ "" ],
					"parameter_enable" : 1,
					"patching_rect" : [ 560.0, 30.0, 20.0, 20.0 ],
					"presentation" : 1,
					"presentation_rect" : [ 340.0, 60.0, 24.0, 16.0 ],
					"saved_attribute_attributes" : {
						"valueof" : {
							"parameter_longname" : "Mute",
							"parameter_shortname" : "Mute",
							"parameter_type" : 2,
							"parameter_mmax" : 1.0,
							"parameter_enum" : [ "Off", "On" ]
						}
					}
				}
			},
			{
				"box" : {
					"id" : "obj-bypass",
					"maxclass" : "live.toggle",
					"varname" : "bypass",
					"numinlets" : 1,
					"numoutlets" : 1,
					"outlettype" : [ "" ],
					"parameter_enable" : 1,
					"patching_rect" : [ 600.0, 30.0, 20.0, 20.0 ],
					"presentation" : 1,
					"presentation_rect" : [ 340.0, 80.0, 24.0, 16.0 ],
					"saved_attribute_attributes" : {
						"valueof" : {
							"parameter_longname" : "Bypass",
							"parameter_shortname" : "Bypass",
							"parameter_type" : 2,
							"parameter_mmax" : 1.0,
							"parameter_enum" : [ "Off", "On" ]
						}
					}
				}
			},
			{
				"box" : {
					"id" : "obj-bypass-msg",
					"maxclass" : "message",
					"text" : "bypass $1",
					"numinlets" : 2,
					"numoutlets" : 1,
					"outlettype" : [ "" ],
					"patching_rect" : [ 600.0, 60.0, 60.0, 20.0 ]
				}
			},

			{
				"box" : {
					"id" : "obj-comment-mute",
					"maxclass" : "comment",
					"text" : "Mute",
					"numinlets" : 1,
					"numoutlets" : 0,
					"presentation" : 1,
					"presentation_rect" : [ 365.0, 61.0, 30.0, 16.0 ],
					"patching_rect" : [ 585.0, 32.0, 30.0, 18.0 ],
					"fontsize" : 8.0,
					"textcolor" : [ 0.6, 0.6, 0.6, 1.0 ]
				}
			},
			{
				"box" : {
					"id" : "obj-comment-bypass",
					"maxclass" : "comment",
					"text" : "Bypass",
					"numinlets" : 1,
					"numoutlets" : 0,
					"presentation" : 1,
					"presentation_rect" : [ 365.0, 81.0, 36.0, 16.0 ],
					"patching_rect" : [ 625.0, 32.0, 36.0, 18.0 ],
					"fontsize" : 8.0,
					"textcolor" : [ 0.6, 0.6, 0.6, 1.0 ]
				}
			},

			{
				"box" : {
					"id" : "obj-jsui-timbre",
					"maxclass" : "jsui",
					"numinlets" : 1,
					"numoutlets" : 1,
					"outlettype" : [ "" ],
					"patching_rect" : [ 700.0, 320.0, 120.0, 50.0 ],
					"filename" : "apollo_timbre_meters.js",
					"presentation" : 1,
					"presentation_rect" : [ 415.0, 5.0, 120.0, 50.0 ]
				}
			},

			{
				"box" : {
					"id" : "obj-jsui-activity",
					"maxclass" : "jsui",
					"numinlets" : 1,
					"numoutlets" : 1,
					"outlettype" : [ "" ],
					"patching_rect" : [ 700.0, 400.0, 40.0, 60.0 ],
					"filename" : "apollo_activity.js",
					"presentation" : 1,
					"presentation_rect" : [ 415.0, 58.0, 40.0, 40.0 ]
				}
			},

			{
				"box" : {
					"id" : "obj-timbre-msg-prefix",
					"maxclass" : "newobj",
					"text" : "prepend timbre",
					"numinlets" : 1,
					"numoutlets" : 1,
					"outlettype" : [ "" ],
					"patching_rect" : [ 700.0, 300.0, 85.0, 20.0 ]
				}
			},

			{
				"box" : {
					"id" : "obj-loadbang",
					"maxclass" : "newobj",
					"text" : "loadbang",
					"numinlets" : 1,
					"numoutlets" : 1,
					"outlettype" : [ "bang" ],
					"patching_rect" : [ 650.0, 30.0, 50.0, 20.0 ]
				}
			},
			{
				"box" : {
					"id" : "obj-comment-title",
					"maxclass" : "comment",
					"text" : "APOLLO",
					"numinlets" : 1,
					"numoutlets" : 0,
					"presentation" : 1,
					"presentation_rect" : [ 460.0, 60.0, 55.0, 18.0 ],
					"patching_rect" : [ 650.0, 5.0, 60.0, 18.0 ],
					"fontname" : "Ableton Sans Bold",
					"fontsize" : 10.0,
					"textcolor" : [ 0.85, 0.85, 0.85, 1.0 ]
				}
			},
			{
				"box" : {
					"id" : "obj-comment-version",
					"maxclass" : "comment",
					"text" : "v0.4.1",
					"numinlets" : 1,
					"numoutlets" : 0,
					"presentation" : 1,
					"presentation_rect" : [ 460.0, 75.0, 40.0, 16.0 ],
					"patching_rect" : [ 650.0, 18.0, 40.0, 18.0 ],
					"fontsize" : 8.0,
					"textcolor" : [ 0.5, 0.5, 0.5, 1.0 ]
				}
			}
		],

		"lines" : [
			{ "patchline" : { "source" : [ "obj-midiin", 0 ], "destination" : [ "obj-midiparse", 0 ] } },
			{ "patchline" : { "source" : [ "obj-midiparse", 0 ], "destination" : [ "obj-input-activity-trigger", 0 ] } },
			{ "patchline" : { "source" : [ "obj-midiparse", 0 ], "destination" : [ "obj-midiformat-passthrough", 0 ] } },
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
			{ "patchline" : { "source" : [ "obj-route-node", 4 ], "destination" : [ "obj-jsui-status", 0 ] } },
			{ "patchline" : { "source" : [ "obj-route-node", 5 ], "destination" : [ "obj-jsui-status", 0 ] } },

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
			"parameterbanks" : {
				"0" : {
					"index" : 0,
					"name" : "Generation",
					"parameters" : [ "Temp", "Top-K", "Density", "Timbre" ]
				},
				"1" : {
					"index" : 1,
					"name" : "Timbral",
					"parameters" : [ "Bright", "Attack", "Rich", "Vel" ]
				},
				"2" : {
					"index" : 2,
					"name" : "Controls",
					"parameters" : [ "Mute", "Bypass", "Engine", "Model" ]
				}
			}
		},

		"dependency_cache" : [
			{ "name" : "apollo_bridge.js", "bootpath" : "../code", "type" : "TEXT" },
			{ "name" : "apollo_status.js", "bootpath" : "../code", "type" : "TEXT" },
			{ "name" : "apollo_timbre_meters.js", "bootpath" : "../code", "type" : "TEXT" },
			{ "name" : "apollo_activity.js", "bootpath" : "../code", "type" : "TEXT" }
		]
	}
}
