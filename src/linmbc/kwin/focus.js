// LinMBC: tell linmbc-daemon which window has focus, so it can switch profiles.
// Loaded at runtime by the daemon through org.kde.KWin /Scripting.loadScript.
// The title is sent too (profiles can match "title:..."), again whenever the
// focused window changes it.

let watched = null;

function report(window) {
    if (!window) {
        return;
    }
    callDBus(
        "io.github.johnsonmauro.LinMBC",
        "/io/github/johnsonmauro/LinMBC",
        "io.github.johnsonmauro.LinMBC.Daemon",
        "SetActiveWindow",
        String(window.resourceClass),
        String(window.resourceName),
        String(window.caption)
    );
}

function reportWatched() {
    report(watched);
}

function activated(window) {
    if (watched) {
        try {
            watched.captionChanged.disconnect(reportWatched);
        } catch (error) {
            // the window was closed; nothing left to disconnect
        }
    }
    watched = window || null;
    if (watched) {
        watched.captionChanged.connect(reportWatched);
    }
    report(watched);
}

workspace.windowActivated.connect(activated);
activated(workspace.activeWindow);
