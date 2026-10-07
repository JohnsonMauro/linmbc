// LinMBC: tell linmbc-daemon which window has focus, so it can switch profiles.
// Loaded at runtime by the daemon through org.kde.KWin /Scripting.loadScript.

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
        String(window.resourceName)
    );
}

workspace.windowActivated.connect(report);
report(workspace.activeWindow);
