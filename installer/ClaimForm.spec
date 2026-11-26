# PyInstaller spec: builds dist\ClaimForm\ClaimForm.exe plus its _internal folder.
# Run build_installer.bat rather than calling PyInstaller by hand.
from pathlib import Path

ROOT = Path(SPECPATH).parent

a = Analysis(
    [str(ROOT / "desktop.py")],
    pathex=[str(ROOT)],
    datas=[
        (str(ROOT / "templates"), "templates"),
        (str(ROOT / "static"), "static"),
    ],
    excludes=["tkinter", "pytest"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ClaimForm",
    icon=str(ROOT / "build" / "ClaimForm.ico"),
    console=True,   # the window shows the address; closing it stops the app
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="ClaimForm", upx=False)
