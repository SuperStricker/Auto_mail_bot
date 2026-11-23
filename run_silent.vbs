Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "cmd /c START_LOCAL.bat", 0, False
Set WshShell = Nothing
