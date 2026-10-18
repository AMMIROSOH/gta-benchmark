"""Build with the installed Visual Studio toolchain; never install or update it."""

import argparse
import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(command, log_name, env=None, cwd=ROOT):
    logs = ROOT / "logs"
    logs.mkdir(exist_ok=True)
    log = logs / log_name
    print(f"Running {Path(command[0]).name}; log: {log}", flush=True)
    with log.open("w", encoding="utf-8") as output:
        result = subprocess.run([str(part) for part in command], cwd=cwd,
                                env=env, stdout=output, stderr=subprocess.STDOUT)
    if result.returncode:
        print(log.read_text(encoding="utf-8", errors="replace")[-10000:])
        raise SystemExit(result.returncode)
    print("Succeeded.", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk-only", action="store_true")
    args = parser.parse_args()
    config = json.loads((ROOT / "config.local.json").read_text())
    sdk = Path(config["plugin_sdk_dir"]).resolve()
    if not (sdk / "shared" / "plugin.h").is_file():
        raise SystemExit(f"Plugin-SDK missing: {sdk}")
    vswhere = Path(os.environ["ProgramFiles(x86)"]) / "Microsoft Visual Studio/Installer/vswhere.exe"
    vs = subprocess.check_output([
        str(vswhere), "-latest", "-products", "*", "-requires",
        "Microsoft.VisualStudio.Component.VC.Tools.x86.x64", "-property", "installationPath"
    ], text=True).strip()
    if not vs:
        raise SystemExit("No installed C++ toolchain found. No toolchain was installed or changed.")
    msbuild = Path(vs) / "MSBuild/Current/Bin/MSBuild.exe"
    env = os.environ.copy()
    env["PLUGIN_SDK_DIR"] = str(sdk)
    env["GTA_SA_DIR"] = config["game_dir"]
    project = sdk / "plugin_sa/Plugin_SA.vcxproj"
    if not project.is_file():
        run([sdk / "tools/premake/premake5.exe", f"--pluginsdkdir={sdk}", "vs2022"],
            "sdk-generate.log", env=env, cwd=sdk / "tools/premake")
    # VS 17.6 crashes when it tries to build its experimental std module with
    # the SDK precompiled header. The SDK uses normal includes, not import std.
    generated = project.read_text(encoding="utf-8-sig")
    if "<BuildStlModules>false</BuildStlModules>" not in generated:
        generated = generated.replace(
            "<LanguageStandard>stdcpplatest</LanguageStandard>",
            "<LanguageStandard>stdcpplatest</LanguageStandard>\n"
            "      <BuildStlModules>false</BuildStlModules>")
        project.write_text(generated, encoding="utf-8-sig")
    run([msbuild, project, "/nologo", "/m:2", "/v:minimal", "/p:Configuration=Release",
         "/p:Platform=Win32", "/p:PlatformToolset=v143", "/p:CL_MPCount=4",
         f"/p:WindowsTargetPlatformVersion={config['windows_sdk_version']}"],
        "sdk-build.log", env=env)
    if args.sdk_only:
        return
    run(["cmake", "-S", ROOT, "-B", ROOT / "build", "-G", "Visual Studio 17 2022",
         "-A", "Win32", "-T", "v143", f"-DPLUGIN_SDK_DIR={sdk}",
         f"-DCMAKE_SYSTEM_VERSION={config['windows_sdk_version']}"], "configure.log", env=env)
    run(["cmake", "--build", ROOT / "build", "--config", "Release", "--parallel", "2"],
        "plugin-build.log", env=env)


if __name__ == "__main__":
    main()
