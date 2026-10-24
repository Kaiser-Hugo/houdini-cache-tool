"""Cache Tool - exporteur de cache versionné pour Houdini.

Exporte la géométrie du nœud SOP sélectionné dans :
    $HIP/cache/<element>/vXXX/<element>_vXXX.<frame>.bgeo.sc
avec un fichier info.json à côté. Ne réécrit jamais une version existante.
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
    """Erreur 'prévue' : on l'affiche proprement à l'artiste au lieu de planter."""


# ---------------------------------------------------------------------------
# Partie 1 : outils de base (déjà testés)
# ---------------------------------------------------------------------------

def clean_name(name):
    """Nettoie un nom d'élément : 'Fumée Rouge' -> 'fumee_rouge'."""
    name = unicodedata.normalize("NFKD", name)            # sépare 'é' en 'e' + accent
    name = name.encode("ascii", "ignore").decode("ascii")  # supprime les accents
    name = name.lower()
    name = re.sub(r"[^a-z0-9]+", "_", name)              # tout ce qui n'est pas lettre/chiffre -> '_'
    return name.strip("_")                               # enlève les '_' au début et à la fin


def next_version(element_dir):
    """Renvoie le numéro de la prochaine version libre dans element_dir."""
    if not os.path.isdir(element_dir):    # le dossier n'existe pas encore -> première version
        return 1
    versions = []
    for folder in os.listdir(element_dir):
        match = re.fullmatch(r"v(\d{3})", folder)   # garde seulement les noms du type v001, v042...
        if match:
            versions.append(int(match.group(1)))     # 'v042' -> 42
    return max(versions, default=0) + 1


# ---------------------------------------------------------------------------
# Partie 2 : vérifications, export et fichier info
# ---------------------------------------------------------------------------

def get_selected_sop():
    """Renvoie le nœud SOP sélectionné, ou lève une CacheToolError."""
    nodes = hou.selectedNodes()
    if not nodes:                                         # tuple vide -> rien de sélectionné
        raise CacheToolError("Sélectionne un nœud SOP avant de lancer l'outil.")
    node = nodes[0]
    if node.type().category().name() != "Sop":            # ex. un nœud /obj ou /out
        raise CacheToolError(f"'{node.path()}' n'est pas un nœud SOP.")
    return node


def write_info(out_dir, node, element, version, frame_range):
    """Écrit info.json à côté du cache."""
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


def export_cache(node, element, start, end, static):
    """Exporte la géométrie et renvoie (dossier de la version, nombre de fichiers)."""
    element_dir = os.path.join(hou.text.expandString("$HIP"), CACHE_FOLDER, element)
    version = next_version(element_dir)
    vtag = f"v{version:03d}"                              # 3 -> 'v003'
    out_dir = os.path.join(element_dir, vtag)
    os.makedirs(out_dir)    # volontairement SANS exist_ok : si le dossier existe, on s'arrête
    base = f"{element}_{vtag}"

    current_frame = hou.frame()                           # on mémorise la frame de l'artiste
    count = 0
    try:
        if static:
            node.geometry().saveToFile(os.path.join(out_dir, base + EXTENSION))
            count = 1
            frame_range = [int(current_frame), int(current_frame)]
        else:
            frames = range(int(start), int(end) + 1)
            with hou.InterruptableOperation(
                    "Export du cache", open_interrupt_dialog=True) as op:
                for i, frame in enumerate(frames):
                    hou.setFrame(frame)                   # Houdini recalcule le nœud à cette frame
                    path = os.path.join(out_dir, f"{base}.{frame:04d}{EXTENSION}")
                    node.geometry().saveToFile(path)
                    count += 1
                    op.updateProgress((i + 1) / len(frames))   # barre de progression
            frame_range = [int(start), int(end)]
    finally:
        hou.setFrame(current_frame)                       # quoi qu'il arrive, on remet la frame

    write_info(out_dir, node, element, version, frame_range)
    return out_dir, count


# ---------------------------------------------------------------------------
# Point d'entrée : c'est ce que lance le bouton de l'étagère
# ---------------------------------------------------------------------------

def run():
    try:
        if hou.hipFile.isNewFile():                       # scène 'untitled' jamais enregistrée
            raise CacheToolError("Enregistre ta scène avant d'exporter un cache.")

        node = get_selected_sop()

        button, text = hou.ui.readInput(
            "Nom de l'élément à cacher :",
            buttons=("OK", "Annuler"),
            default_choice=0, close_choice=1,
            initial_contents=node.name())
        if button == 1:
            return
        element = clean_name(text)
        if not element:
            raise CacheToolError("Le nom de l'élément est vide.")

        choice = hou.ui.displayMessage(
            f"Type de cache pour '{element}' ?",
            buttons=("Animé (plage de la timeline)", "Statique (frame actuelle)", "Annuler"),
            default_choice=0, close_choice=2)
        if choice == 2:
            return
        static = (choice == 1)

        start, end = hou.playbar.frameRange()
        out_dir, count = export_cache(node, element, start, end, static)
        hou.ui.displayMessage(f"{count} fichier(s) écrit(s) dans :\n{out_dir}")

    except CacheToolError as e:
        hou.ui.displayMessage(str(e), severity=hou.severityType.Error)
    except hou.OperationInterrupted:
        hou.ui.displayMessage("Export annulé. Le dossier de version est incomplet.",
                              severity=hou.severityType.Warning)