use std::env;
use std::fs::{self, File};
use std::io::Cursor;
use std::path::{Component, Path, PathBuf};
use std::process::{Command, ExitCode, Stdio};

use flate2::read::GzDecoder;
use serde::Deserialize;
use sha2::{Digest, Sha256};
use tar::Archive;

static BUNDLE: &[u8] = include_bytes!(env!("SOCIUM_BUNDLE_PATH"));
const EXPECTED_SHA256: &str = env!("SOCIUM_BUNDLE_SHA256");
const RELEASE_TARGET: &str = env!("SOCIUM_RELEASE_TARGET");
const RELEASE_VERSION: &str = env!("SOCIUM_RELEASE_VERSION");
const RELEASE_MANIFEST: &str = env!("SOCIUM_RELEASE_MANIFEST");

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct BundleMetadata {
    schema_version: u8,
    product: String,
    version: String,
    target: String,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct Installation {
    runtime_path: PathBuf,
}

#[derive(Default)]
struct Arguments {
    home: Option<PathBuf>,
    data_dir: Option<PathBuf>,
    models_dir: Option<PathBuf>,
    install_only: bool,
    no_shortcuts: bool,
    autostart: bool,
}

impl Arguments {
    fn parse() -> Result<Self, String> {
        let mut result = Self::default();
        let mut values = env::args().skip(1);
        while let Some(argument) = values.next() {
            match argument.as_str() {
                "--home" => result.home = Some(PathBuf::from(values.next().ok_or("--home requires a path")?)),
                "--data-dir" => result.data_dir = Some(PathBuf::from(values.next().ok_or("--data-dir requires a path")?)),
                "--models-dir" => result.models_dir = Some(PathBuf::from(values.next().ok_or("--models-dir requires a path")?)),
                "--install-only" => result.install_only = true,
                "--no-shortcuts" => result.no_shortcuts = true,
                "--autostart" => result.autostart = true,
                "--version" | "-v" => {
                    println!("{RELEASE_VERSION}");
                    std::process::exit(0);
                }
                "--help" | "-h" => {
                    println!("Socium Setup {RELEASE_VERSION}\n\nDouble-click to install and open Socium.\n\nAdvanced options:\n  --home PATH\n  --data-dir PATH\n  --models-dir PATH\n  --autostart\n  --no-shortcuts\n  --install-only");
                    std::process::exit(0);
                }
                _ => return Err(format!("Unknown option: {argument}")),
            }
        }
        Ok(result)
    }
}

fn application_root(arguments: &Arguments) -> Result<PathBuf, String> {
    if let Some(root) = &arguments.home {
        return Ok(root.clone());
    }
    if let Some(root) = env::var_os("SOCIUM_HOME").filter(|value| !value.is_empty()) {
        return Ok(PathBuf::from(root));
    }
    let home = env::var_os(if cfg!(windows) { "USERPROFILE" } else { "HOME" })
        .map(PathBuf::from)
        .ok_or("Could not determine the current user's home directory")?;
    if cfg!(windows) {
        Ok(env::var_os("LOCALAPPDATA")
            .map(PathBuf::from)
            .unwrap_or_else(|| home.join("AppData").join("Local"))
            .join("Socium"))
    } else if cfg!(target_os = "macos") {
        Ok(home.join("Library").join("Application Support").join("Socium"))
    } else {
        Ok(env::var_os("XDG_DATA_HOME")
            .map(PathBuf::from)
            .unwrap_or_else(|| home.join(".local").join("share"))
            .join("socium"))
    }
}

fn verify_embedded_bundle() -> Result<(), String> {
    let actual = format!("{:x}", Sha256::digest(BUNDLE));
    if !actual.eq_ignore_ascii_case(EXPECTED_SHA256) {
        return Err("The embedded Socium runtime failed checksum verification".to_string());
    }
    Ok(())
}

fn safe_relative_path(path: &Path) -> bool {
    !path.is_absolute()
        && path.components().all(|component| matches!(component, Component::Normal(_) | Component::CurDir))
}

fn extract_bundle(destination: &Path) -> Result<(), String> {
    let decoder = GzDecoder::new(Cursor::new(BUNDLE));
    let mut archive = Archive::new(decoder);
    let entries = archive.entries().map_err(|error| format!("Could not read the embedded runtime: {error}"))?;
    for entry in entries {
        let mut entry = entry.map_err(|error| format!("Could not read a runtime entry: {error}"))?;
        let path = entry.path().map_err(|error| format!("Invalid runtime path: {error}"))?.into_owned();
        if !safe_relative_path(&path) || entry.header().entry_type().is_symlink() || entry.header().entry_type().is_hard_link() {
            return Err(format!("The embedded runtime contains an unsafe path: {}", path.display()));
        }
        entry.unpack_in(destination).map_err(|error| format!("Could not install {}: {error}", path.display()))?;
    }
    Ok(())
}

fn validate_runtime(runtime: &Path) -> Result<(), String> {
    let metadata: BundleMetadata = serde_json::from_reader(
        File::open(runtime.join("bundle.json")).map_err(|error| format!("Could not read bundle metadata: {error}"))?,
    )
    .map_err(|error| format!("Invalid bundle metadata: {error}"))?;
    if metadata.schema_version != 3 || metadata.product != "socium" || metadata.version != RELEASE_VERSION || metadata.target != RELEASE_TARGET {
        return Err("The embedded runtime metadata does not match this installer".to_string());
    }
    let platform = RELEASE_TARGET.split('-').next().unwrap_or_default();
    let node = runtime.join("bin").join(if platform == "win32" { "node.exe" } else { "node" });
    let api = runtime.join("backend").join(if platform == "win32" { "socium-api.exe" } else { "socium-api" });
    for required in [node, api, runtime.join("web").join("server.js"), runtime.join("controller").join("offline-install.mjs")] {
        if !required.is_file() {
            return Err(format!("The embedded runtime is missing {}", required.display()));
        }
    }
    Ok(())
}

fn install_runtime(root: &Path) -> Result<PathBuf, String> {
    verify_embedded_bundle()?;
    let runtime = root.join("runtimes").join(RELEASE_VERSION).join(RELEASE_TARGET);
    if runtime.is_dir() && validate_runtime(&runtime).is_ok() {
        return Ok(runtime);
    }
    let staging = root.join("runtimes").join(RELEASE_VERSION).join(format!("{RELEASE_TARGET}.installer-{}", std::process::id()));
    if staging.exists() {
        fs::remove_dir_all(&staging).map_err(|error| format!("Could not clear incomplete setup files: {error}"))?;
    }
    fs::create_dir_all(&staging).map_err(|error| format!("Could not create setup directory: {error}"))?;
    let result = (|| {
        extract_bundle(&staging)?;
        validate_runtime(&staging)?;
        if runtime.exists() {
            fs::remove_dir_all(&runtime).map_err(|error| format!("Could not replace an incomplete runtime: {error}"))?;
        }
        fs::rename(&staging, &runtime).map_err(|error| format!("Could not activate the Socium runtime: {error}"))?;
        Ok(runtime.clone())
    })();
    if result.is_err() {
        let _ = fs::remove_dir_all(&staging);
    }
    result
}

fn register_installation(root: &Path, runtime: &Path, arguments: &Arguments) -> Result<PathBuf, String> {
    let platform = RELEASE_TARGET.split('-').next().unwrap_or_default();
    let node = runtime.join("bin").join(if platform == "win32" { "node.exe" } else { "node" });
    let script = runtime.join("controller").join("offline-install.mjs");
    let mut command = Command::new(&node);
    command
        .arg(script)
        .arg("--runtime-path").arg(runtime)
        .arg("--version").arg(RELEASE_VERSION)
        .arg("--target").arg(RELEASE_TARGET)
        .arg("--manifest").arg(RELEASE_MANIFEST)
        .env("SOCIUM_HOME", root);
    if let Some(value) = &arguments.data_dir { command.arg("--data-dir").arg(value); }
    if let Some(value) = &arguments.models_dir { command.arg("--models-dir").arg(value); }
    if arguments.no_shortcuts { command.arg("--no-shortcuts"); }
    if arguments.autostart { command.arg("--autostart"); }
    let output = command.output().map_err(|error| format!("Could not finalize the installation: {error}"))?;
    if !output.status.success() {
        return Err(String::from_utf8_lossy(&output.stderr).trim().to_string());
    }
    let installation: Installation = serde_json::from_reader(
        File::open(root.join("installation.json")).map_err(|error| format!("Could not read the installation record: {error}"))?,
    )
    .map_err(|error| format!("Invalid installation record: {error}"))?;
    Ok(installation.runtime_path)
}

fn launch(root: &Path, runtime: &Path) -> Result<(), String> {
    let platform = RELEASE_TARGET.split('-').next().unwrap_or_default();
    let node = runtime.join("bin").join(if platform == "win32" { "node.exe" } else { "node" });
    let mut command = Command::new(node);
    command
        .arg(runtime.join("controller").join("controller.mjs"))
        .arg("start")
        .arg("--tray")
        .current_dir(runtime)
        .env("SOCIUM_HOME", root)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());
    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x08000008);
    }
    command.spawn().map_err(|error| format!("Socium was installed but could not start: {error}"))?;
    Ok(())
}

fn run() -> Result<(), String> {
    let arguments = Arguments::parse()?;
    let root = application_root(&arguments)?;
    println!("Installing Socium {RELEASE_VERSION}...");
    let embedded_runtime = install_runtime(&root)?;
    let active_runtime = register_installation(&root, &embedded_runtime, &arguments)?;
    if !arguments.install_only {
        launch(&root, &active_runtime)?;
        println!("Socium is installed and opening in your browser.");
    } else {
        println!("Socium is installed at {}", active_runtime.display());
    }
    Ok(())
}

fn main() -> ExitCode {
    match run() {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => {
            eprintln!("Socium setup failed: {error}");
            ExitCode::FAILURE
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rejects_parent_and_absolute_archive_paths() {
        assert!(!safe_relative_path(Path::new("../escape")));
        assert!(!safe_relative_path(Path::new("/absolute")));
        assert!(safe_relative_path(Path::new("controller/offline-install.mjs")));
    }
}
