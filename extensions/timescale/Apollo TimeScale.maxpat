{
	"patcher": {
		"fileversion": 1,
		"appversion": {
			"major": 8,
			"minor": 6,
			"revision": 0,
			"architecture": "x64",
			"modernui": 1
		},
		"classnamespace": "box",
		"rect": [
			100.0,
			100.0,
			640.0,
			420.0
		],
		"openinpresentation": 1,
		"default_fontsize": 10.0,
		"default_fontname": "Arial Bold",
		"gridsize": [
			8.0,
			8.0
		],
		"boxes": [
			{
				"box": {
					"id": "obj-dial",
					"maxclass": "live.dial",
					"numinlets": 1,
					"numoutlets": 2,
					"outlettype": [
						"",
						"float"
					],
					"parameter_enable": 1,
					"patching_rect": [
						32.0,
						32.0,
						44.0,
						48.0
					],
					"presentation": 1,
					"presentation_rect": [
						8.0,
						8.0,
						44.0,
						48.0
					],
					"saved_attribute_attributes": {
						"valueof": {
							"parameter_longname": "Time Scale",
							"parameter_shortname": "Time",
							"parameter_type": 0,
							"parameter_mmin": -50.0,
							"parameter_mmax": 50.0,
							"parameter_initial_enable": 1,
							"parameter_initial": [
								0.0
							],
							"parameter_unitstyle": 5
						}
					},
					"varname": "Time Scale"
				}
			},
			{
				"box": {
					"id": "obj-prepend",
					"maxclass": "newobj",
					"numinlets": 1,
					"numoutlets": 1,
					"outlettype": [
						""
					],
					"patching_rect": [
						32.0,
						104.0,
						80.0,
						20.0
					],
					"text": "prepend scale"
				}
			},
			{
				"box": {
					"id": "obj-thisdevice",
					"maxclass": "newobj",
					"numinlets": 1,
					"numoutlets": 3,
					"outlettype": [
						"bang",
						"int",
						"int"
					],
					"patching_rect": [
						200.0,
						32.0,
						90.0,
						20.0
					],
					"text": "live.thisdevice"
				}
			},
			{
				"box": {
					"id": "obj-defer",
					"maxclass": "newobj",
					"numinlets": 1,
					"numoutlets": 1,
					"outlettype": [
						""
					],
					"patching_rect": [
						32.0,
						144.0,
						56.0,
						20.0
					],
					"text": "deferlow"
				}
			},
			{
				"box": {
					"id": "obj-js",
					"maxclass": "newobj",
					"numinlets": 1,
					"numoutlets": 1,
					"outlettype": [
						""
					],
					"patching_rect": [
						32.0,
						184.0,
						150.0,
						20.0
					],
					"saved_object_attributes": {
						"filename": "apollo_timescale.js",
						"parameter_enable": 0
					},
					"text": "js apollo_timescale.js"
				}
			},
			{
				"box": {
					"id": "obj-status",
					"maxclass": "message",
					"numinlets": 2,
					"numoutlets": 1,
					"outlettype": [
						""
					],
					"patching_rect": [
						32.0,
						224.0,
						200.0,
						20.0
					],
					"presentation": 1,
					"presentation_rect": [
						60.0,
						24.0,
						160.0,
						20.0
					],
					"text": "loading..."
				}
			},
			{
				"box": {
					"id": "obj-trig",
					"maxclass": "newobj",
					"numinlets": 1,
					"numoutlets": 2,
					"outlettype": [
						"bang",
						"bang"
					],
					"patching_rect": [
						200.0,
						64.0,
						40.0,
						20.0
					],
					"text": "t b b"
				}
			}
		],
		"lines": [
			{
				"patchline": {
					"source": [
						"obj-dial",
						0
					],
					"destination": [
						"obj-prepend",
						0
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-prepend",
						0
					],
					"destination": [
						"obj-defer",
						0
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-defer",
						0
					],
					"destination": [
						"obj-js",
						0
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-js",
						0
					],
					"destination": [
						"obj-status",
						0
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-thisdevice",
						0
					],
					"destination": [
						"obj-trig",
						0
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-trig",
						1
					],
					"destination": [
						"obj-dial",
						0
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-trig",
						0
					],
					"destination": [
						"obj-defer",
						0
					]
				}
			}
		],
		"dependency_cache": [
			{
				"name": "apollo_timescale.js",
				"bootpath": ".",
				"type": "TEXT",
				"implicit": 1
			}
		]
	}
}