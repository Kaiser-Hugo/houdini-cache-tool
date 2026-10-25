"""Cache Tool - versioned geometry cache exporter for Houdini.

Exports the selected SOP node to:
    $HIP/cache/<element>/vXXX/<element>_vXXX.<frame>.bgeo.sc
along with an info.json file. Existing versions are never overwritten.
"""
import datetime
import getpass
import json
import os
import re
import unicodedata

import hou

CACHE_FOLDER = "cache"
EXTENSION = ".bgeo.sc"


class CacheToolError(Exception):
	"""Expected error, shown to the artist as a clean message instead of a crash."""


def clean_name(name: str) -> str:
	"""Sanitize an element name: 'Fumée Rouge' -> 'fumee_rouge'."""
	name = unicodedata.normalize("NFKD", name)  # split 'é' into 'e' + accent
	name = name.encode("ascii", "ignore").decode("ascii")  # drop the accents
	name = name.lower()
	name = re.sub(r"[^a-z0-9]+", "_", name)  # anything but letters/digits -> '_'
	return name.strip("_")


def next_version(element_dir):
	"""Return the next version in element_dir"""
	if not os.path.isdir(element_dir):  # no folder yet -> first version
		return 1
	versions = []
	for folder in os.listdir(element_dir):
		match = re.fullmatch(r"v(\d{3})", folder)
		if match:
			versions.append(int(match.group(1)))  # 'v042' -> 42
	return max(versions, default=0) + 1


def list_versions(element_dir):
	"""Return the sorted list of version folders (v001, v002...) in element_dir."""
	if not os.path.isdir(element_dir):  # no folder yet -> no versions
		return []
	versions = []
	for folder in os.listdir(element_dir):
		match = re.fullmatch(r"v(\d{3})", folder)
		if match:
			versions.append(folder)
	return sorted(versions)


def check_scene_saved():
	"""Raise a CacheToolError if the scene has never been saved."""
	if hou.hipFile.isNewFile():
		raise CacheToolError("Save your scene before exporting a cache.")


def validate_element_name(text):
	"""Return a valid element name or raise a CacheToolError if the name is empty."""
	element = clean_name(text)
	if not element:
		raise CacheToolError("The element name is empty.")
	return element


def report_errors(func):
	"""Decorator: show expected errors to the artist instead of crashing."""

	def wrapper(*args, **kwargs):
		try:
			return func(*args, **kwargs)
		except CacheToolError as e:
			hou.ui.displayMessage(str(e), severity=hou.severityType.Error)
		except hou.OperationInterrupted:
			hou.ui.displayMessage("Export cancelled. This version folder is incomplete.",
								  severity=hou.severityType.Warning)

	return wrapper


def get_selected_sop():
	"""Return the selected SOP node, or raise a CacheToolError."""
	nodes = hou.selectedNodes()
	if not nodes:
		raise CacheToolError("Select a SOP node before running the tool.")
	node = nodes[0]
	if node.type().category().name() != "Sop":  # e.g. an /obj or /out node
		raise CacheToolError(f"'{node.path()}' is not a SOP node.")
	return node


def write_info(out_dir, node, element, version, frame_range):
	"""Write json file in the cache folder"""
	info = {
		"element": element,
		"version": version,
		"user": getpass.getuser(),
		"date": datetime.datetime.now().isoformat(timespec="seconds"),
		"hip_file": hou.hipFile.path(),
		"node": node.path(),
		"frame_range": frame_range,
		"houdini_version": hou.applicationVersionString(),
	}
	with open(os.path.join(out_dir, "info.json"), "w", encoding="utf-8") as f:
		json.dump(info, f, indent=4, ensure_ascii=False)


def read_info(version_dir):
	"""Return the content of info.json in version_dir, or an empty dict."""
	path = os.path.join(version_dir, "info.json")
	if not os.path.isfile(path):
		return {}
	with open(path, "r", encoding="utf-8") as f:
		return json.load(f)


def build_cache_path(element, vtag, static):
	"""Return the Houdini path of a cached version ($F4 for animated caches)."""
	base = f"{element}_{vtag}"
	folder = f"$HIP/{CACHE_FOLDER}/{element}/{vtag}"
	if static:
		filename = f"{base}{EXTENSION}"
	else:
		filename = f"{base}.$F4{EXTENSION}"
	return os.path.join(folder, filename)


def version_menu(hda_node):
	"""Return the flat [token, label, ...] list for the HDA's Version menu."""
	element = clean_name(hda_node.evalParm("element"))
	element_dir = os.path.join(hou.text.expandString("$HIP"), CACHE_FOLDER, element)
	menu = []
	for vtag in list_versions(element_dir):
		info = read_info(os.path.join(element_dir, vtag))
		date = info.get("date", "")
		frame_range = info.get("frame_range")
		if frame_range:
			start, end = frame_range
			if start == end:
				kind = "[static]"
			else:
				kind = f"[anim {start}-{end}]"
		else:
			kind = ""
		if date:
			short_date = date.replace("T", "/")[:16]
			label = f"{vtag} {kind} ({short_date})"
		else:
			label =f"{vtag} {kind}"
		menu.extend([vtag, label])
	return menu


@report_errors
def hda_load(hda_node):
	"""Called by the Load button: create a File SOP reading the chosen version."""
	element = validate_element_name(hda_node.evalParm("element"))
	vtag = hda_node.evalParm("version")
	if not vtag:
		raise CacheToolError("Choose a version to load.")
	element_dir = os.path.join(hou.text.expandString("$HIP"), CACHE_FOLDER, element)
	info = read_info(os.path.join(element_dir, vtag))
	if "frame_range" not in info:
		raise CacheToolError("The export was probably cancelled")
	start, end = info["frame_range"]
	static = (start == end)
	path = build_cache_path(element, vtag, static)
	parent = hda_node.parent()
	node_name = f"{element}_{vtag}"
	existing = parent.node(node_name)
	if existing:
		existing.setSelected(True, clear_all_selected=True)
		hou.ui.displayMessage(f"{node_name} is already loaded.")
		return
	file_node = parent.createNode("file", node_name)
	file_node.parm("file").set(path)
	file_node.setPosition(hda_node.position() + hou.Vector2(3, 0))


def export_cache(node, element, start, end, static):
	"""Export the node's geometry and return (version folder, file count)."""
	element_dir = os.path.join(hou.text.expandString("$HIP"), CACHE_FOLDER, element)
	version = next_version(element_dir)
	vtag = f"v{version:03d}"  # 3 -> 'v003'
	out_dir = os.path.join(element_dir, vtag)
	# No exist_ok on purpose: fail rather than overwrite an existing version.
	os.makedirs(out_dir)
	base = f"{element}_{vtag}"

	current_frame = hou.frame()
	count = 0
	try:
		if static:
			node.geometry().saveToFile(os.path.join(out_dir, base + EXTENSION))
			count = 1
			frame_range = [int(current_frame), int(current_frame)]
		else:
			frames = range(int(start), int(end) + 1)
			with hou.InterruptableOperation(
					"Exporting cache", open_interrupt_dialog=True) as op:
				for i, frame in enumerate(frames):
					hou.setFrame(frame)  # Houdini recooks the node at this frame
					path = os.path.join(out_dir, f"{base}.{frame:04d}{EXTENSION}")
					node.geometry().saveToFile(path)
					count += 1
					op.updateProgress((i + 1) / len(frames))
			frame_range = [int(start), int(end)]
	finally:
		hou.setFrame(current_frame)

	write_info(out_dir, node, element, version, frame_range)
	return out_dir, count


@report_errors
def run():
	check_scene_saved()

	node = get_selected_sop()

	button, text = hou.ui.readInput(
		"Element name to cache:",
		buttons=("OK", "Cancel"),
		default_choice=0, close_choice=1,
		initial_contents=node.name())
	if button == 1:
		return
	element = validate_element_name(text)

	choice = hou.ui.displayMessage(
		f"Cache type for '{element}'?",
		buttons=("Animated (timeline range)", "Static (current frame)", "Cancel"),
		default_choice=0, close_choice=2)
	if choice == 2:
		return
	static = (choice == 1)

	start, end = hou.playbar.frameRange()
	out_dir, count = export_cache(node, element, start, end, static)
	hou.ui.displayMessage(f"{count} file(s) written to:\n{out_dir}")


@report_errors
def hda_export(hda_node):
	"""Called by the Export button of the Cache Export HDA."""
	check_scene_saved()

	if not hda_node.inputs():
		raise CacheToolError("Connect a node to the Cache Export input.")

	element = validate_element_name(hda_node.evalParm("element"))

	static = bool(hda_node.evalParm("static"))
	start, end = hda_node.evalParmTuple("frange")

	out_dir, count = export_cache(hda_node, element, start, end, static)
	hou.ui.displayMessage(f"{count} file(s) written to:\n{out_dir}")
