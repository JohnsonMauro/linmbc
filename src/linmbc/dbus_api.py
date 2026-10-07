"""D-Bus names shared by the daemon, the GUI and (later) the KWin script.

Methods (interface INTERFACE, object OBJECT_PATH on the session bus):
    GetState() -> s            JSON, see Service.state() plus "log_path"
    SetEnabled(b)
    SetDefaultProfile(s)       profile used outside games; "" = buttons unchanged
    SetActiveWindow(ss)        window class, resource name (called by the KWin script)
    ReloadProfiles()
    Quit()
Signals:
    StateChanged(s)            same JSON as GetState
    Log(s)                     one formatted log line
    Button(s device_key, s button_name, i value)   every physical press/release
"""

BUS_NAME = "io.github.johnsonmauro.LinMBC"
OBJECT_PATH = "/io/github/johnsonmauro/LinMBC"
INTERFACE = "io.github.johnsonmauro.LinMBC.Daemon"
ERROR_INVALID = "io.github.johnsonmauro.LinMBC.Error.Invalid"
