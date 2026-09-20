Option Explicit
Dim shell, fso, base, scriptPath, cmd
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
base = fso.GetParentFolderName(WScript.ScriptFullName)
scriptPath = base & "\\PVZ_Replanted_CUSA55613_Save_Editor.pyw"
shell.CurrentDirectory = base

On Error Resume Next
cmd = "pyw.exe -3 """ & scriptPath & """"
shell.Run cmd, 0, False
If Err.Number = 0 Then WScript.Quit 0
Err.Clear
cmd = "pythonw.exe """ & scriptPath & """"
shell.Run cmd, 0, False
If Err.Number = 0 Then WScript.Quit 0
On Error GoTo 0

MsgBox "Python 3 with Tkinter was not found. Install standard Python 3, then open this launcher again.", 16, "PvZ Save Editor"
