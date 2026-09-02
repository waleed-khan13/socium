use std::env;
use std::fs;
use std::io::{Read, Write};
use std::net::TcpStream;
use std::path::{Path, PathBuf};
use std::process::ExitCode;
use std::thread;
use std::time::Duration;

use serde::Deserialize;
use serde_json::json;

#[cfg(target_os = "windows")]
use tray_icon::{
    Icon, TrayIconBuilder, TrayIconEvent,
    menu::{Menu, MenuEvent, MenuItem},
};
#[cfg(target_os = "windows")]
use windows::{
    Win32::{
        System::Com::{
            CLSCTX_INPROC_SERVER, COINIT_APARTMENTTHREADED, CoCreateInstance, CoInitializeEx,
            CoUninitialize, IPersistFile,
        },
        UI::Shell::{IShellLinkW, ShellLink},
    },
    core::{HSTRING, Interface, PCWSTR},
};

#[derive(Debug)]
struct Arguments {
    command: String,
    values: Vec<String>,
}

impl Arguments {
    fn parse() -> Result<Self, String> {
        let mut raw = env::args().skip(1);
        let command = raw.next().ok_or_else(help)?;
        Ok(Self {
            command,
            values: raw.collect(),
        })
    }

    fn value(&self, name: &str) -> Result<String, String> {
        let index = self
            .values
            .iter()
            .position(|item| item == name)
            .ok_or_else(|| format!("{name} is required."))?;
        self.values
            .get(index + 1)
            .filter(|value| !value.starts_with("--"))
            .cloned()
            .ok_or_else(|| format!("{name} requires a value."))
    }

    fn optional(&self, name: &str) -> Option<String> {
        let index = self.values.iter().position(|item| item == name)?;
        self.values
            .get(index + 1)
            .filter(|value| !value.starts_with("--"))
            .cloned()
    }
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct RuntimeState {
    web_port: u16,
    control_port: u16,
    control_token: String,
    version: String,
}

fn help() -> String {
    [
        "Socium Windows helper",
        "",
        "Commands:",
        "  tray --state-file <path>",
        "  pick-folder --title <title> --initial <path>",
        "  create-shortcut --path <lnk> --target <exe> --arguments <args> --working-directory <path> [--description <text>]",
        "  remove-shortcut --path <lnk>",
        "  version",
    ]
    .join("\n")
}

fn print_json(value: serde_json::Value) {
    println!("{value}");
}

fn read_runtime_state(path: &Path) -> Result<RuntimeState, String> {
    let bytes = fs::read(path).map_err(|error| format!("Could not read runtime state: {error}"))?;
    serde_json::from_slice(&bytes).map_err(|error| format!("Invalid runtime state: {error}"))
}

fn open_dashboard(state_file: &Path) -> Result<(), String> {
    let state = read_runtime_state(state_file)?;
    open_url(&format!("http://127.0.0.1:{}", state.web_port))
}

#[cfg(target_os = "windows")]
fn open_url(url: &str) -> Result<(), String> {
    use windows::Win32::UI::Shell::ShellExecuteW;
    use windows::Win32::UI::WindowsAndMessaging::SW_SHOWNORMAL;

    let operation = HSTRING::from("open");
    let target = HSTRING::from(url);
    let result = unsafe {
        ShellExecuteW(
            None,
            PCWSTR(operation.as_ptr()),
            PCWSTR(target.as_ptr()),
            None,
            None,
            SW_SHOWNORMAL,
        )
    };
    if result.0 as isize <= 32 {
        return Err("Windows could not open the Socium dashboard.".to_string());
    }
    Ok(())
}

#[cfg(not(target_os = "windows"))]
fn open_url(_url: &str) -> Result<(), String> {
    Err("This helper only supports Windows.".to_string())
}

fn send_control_action(state_file: &Path, action: &str) -> Result<(), String> {
    let state = read_runtime_state(state_file)?;
    let mut stream = TcpStream::connect(("127.0.0.1", state.control_port))
        .map_err(|error| format!("Could not reach the Socium controller: {error}"))?;
    stream
        .set_read_timeout(Some(Duration::from_secs(5)))
        .map_err(|error| error.to_string())?;
    stream
        .set_write_timeout(Some(Duration::from_secs(5)))
        .map_err(|error| error.to_string())?;
    let request = format!(
        "POST /{action} HTTP/1.1\r\nHost: 127.0.0.1:{}\r\nAuthorization: Bearer {}\r\nContent-Length: 0\r\nConnection: close\r\n\r\n",
        state.control_port, state.control_token
    );
    stream
        .write_all(request.as_bytes())
        .map_err(|error| format!("Could not send {action}: {error}"))?;
    let mut response = String::new();
    stream
        .read_to_string(&mut response)
        .map_err(|error| format!("Could not read controller response: {error}"))?;
    if !response.starts_with("HTTP/1.1 200") {
        return Err(format!("Socium controller rejected {action}."));
    }
    Ok(())
}

#[cfg(target_os = "windows")]
fn helper_icon() -> Result<Icon, String> {
    const SIZE: u32 = 32;
    let mut rgba = vec![0_u8; (SIZE * SIZE * 4) as usize];
    for y in 0..SIZE {
        for x in 0..SIZE {
            let index = ((y * SIZE + x) * 4) as usize;
            let border = x < 2 || y < 2 || x >= SIZE - 2 || y >= SIZE - 2;
            let diagonal = ((x as i32 - y as i32).abs() <= 2 && x > 6 && x < 25)
                || (((SIZE - 1 - x) as i32 - y as i32).abs() <= 2 && x > 6 && x < 25);
            let (red, green, blue) = if diagonal {
                (245, 158, 11)
            } else if border {
                (63, 63, 70)
            } else {
                (5, 5, 5)
            };
            rgba[index] = red;
            rgba[index + 1] = green;
            rgba[index + 2] = blue;
            rgba[index + 3] = 255;
        }
    }
    Icon::from_rgba(rgba, SIZE, SIZE).map_err(|error| error.to_string())
}

#[cfg(target_os = "windows")]
fn run_tray(state_file: PathBuf) -> Result<(), String> {
    let state = read_runtime_state(&state_file)?;
    let menu = Menu::new();
    let status = MenuItem::new(format!("Socium {} is running", state.version), false, None);
    let open = MenuItem::new("Open dashboard", true, None);
    let restart = MenuItem::new("Restart", true, None);
    let stop = MenuItem::new("Stop Socium", true, None);
    let exit = MenuItem::new("Exit tray", true, None);
    menu.append_items(&[&status, &open, &restart, &stop, &exit])
        .map_err(|error| error.to_string())?;
    let _tray = TrayIconBuilder::new()
        .with_tooltip(format!("Socium {}", state.version))
        .with_icon(helper_icon()?)
        .with_menu(Box::new(menu))
        .build()
        .map_err(|error| error.to_string())?;

    loop {
        while let Ok(event) = MenuEvent::receiver().try_recv() {
            if event.id == open.id() {
                let _ = open_dashboard(&state_file);
            } else if event.id == restart.id() {
                send_control_action(&state_file, "restart")?;
                return Ok(());
            } else if event.id == stop.id() {
                send_control_action(&state_file, "stop")?;
                return Ok(());
            } else if event.id == exit.id() {
                return Ok(());
            }
        }
        while let Ok(event) = TrayIconEvent::receiver().try_recv() {
            if matches!(event, TrayIconEvent::DoubleClick { .. }) {
                let _ = open_dashboard(&state_file);
            }
        }
        if !state_file.exists() {
            return Ok(());
        }
        thread::sleep(Duration::from_millis(100));
    }
}

#[cfg(not(target_os = "windows"))]
fn run_tray(_state_file: PathBuf) -> Result<(), String> {
    Err("This helper only supports Windows.".to_string())
}

fn pick_folder(title: &str, initial: &Path) -> Result<(), String> {
    let mut dialog = rfd::FileDialog::new().set_title(title);
    if initial.is_dir() {
        dialog = dialog.set_directory(initial);
    }
    let selection = dialog.pick_folder();
    print_json(json!({ "path": selection.map(|path| path.to_string_lossy().to_string()) }));
    Ok(())
}

#[cfg(target_os = "windows")]
fn with_com<T>(operation: impl FnOnce() -> Result<T, String>) -> Result<T, String> {
    unsafe {
        CoInitializeEx(None, COINIT_APARTMENTTHREADED)
            .ok()
            .map_err(|error| format!("Could not initialize Windows COM: {error}"))?;
    }
    let result = operation();
    unsafe { CoUninitialize() };
    result
}

#[cfg(target_os = "windows")]
fn create_shortcut(
    shortcut: &Path,
    target: &Path,
    arguments: &str,
    working_directory: &Path,
    description: &str,
) -> Result<(), String> {
    if let Some(parent) = shortcut.parent() {
        fs::create_dir_all(parent)
            .map_err(|error| format!("Could not create shortcut directory: {error}"))?;
    }
    with_com(|| unsafe {
        let link: IShellLinkW = CoCreateInstance(&ShellLink, None, CLSCTX_INPROC_SERVER)
            .map_err(|error| format!("Could not create Windows shortcut: {error}"))?;
        let target = HSTRING::from(target.as_os_str());
        let arguments = HSTRING::from(arguments);
        let working_directory = HSTRING::from(working_directory.as_os_str());
        let description = HSTRING::from(description);
        link.SetPath(PCWSTR(target.as_ptr()))
            .map_err(|error| error.to_string())?;
        link.SetArguments(PCWSTR(arguments.as_ptr()))
            .map_err(|error| error.to_string())?;
        link.SetWorkingDirectory(PCWSTR(working_directory.as_ptr()))
            .map_err(|error| error.to_string())?;
        link.SetDescription(PCWSTR(description.as_ptr()))
            .map_err(|error| error.to_string())?;
        let persist: IPersistFile = link
            .cast()
            .map_err(|error| format!("Could not persist Windows shortcut: {error}"))?;
        let shortcut = HSTRING::from(shortcut.as_os_str());
        persist
            .Save(PCWSTR(shortcut.as_ptr()), true)
            .map_err(|error| format!("Could not save Windows shortcut: {error}"))?;
        Ok(())
    })?;
    print_json(json!({ "ok": true, "path": shortcut.to_string_lossy() }));
    Ok(())
}

#[cfg(not(target_os = "windows"))]
fn create_shortcut(
    _shortcut: &Path,
    _target: &Path,
    _arguments: &str,
    _working_directory: &Path,
    _description: &str,
) -> Result<(), String> {
    Err("This helper only supports Windows.".to_string())
}

fn run(arguments: Arguments) -> Result<(), String> {
    match arguments.command.as_str() {
        "version" | "--version" | "-v" => {
            println!(env!("CARGO_PKG_VERSION"));
            Ok(())
        }
        "tray" => run_tray(PathBuf::from(arguments.value("--state-file")?)),
        "pick-folder" => pick_folder(
            &arguments.value("--title")?,
            Path::new(&arguments.value("--initial")?),
        ),
        "create-shortcut" => create_shortcut(
            Path::new(&arguments.value("--path")?),
            Path::new(&arguments.value("--target")?),
            &arguments.value("--arguments")?,
            Path::new(&arguments.value("--working-directory")?),
            &arguments
                .optional("--description")
                .unwrap_or_else(|| "Start Socium".to_string()),
        ),
        "remove-shortcut" => {
            let path = PathBuf::from(arguments.value("--path")?);
            match fs::remove_file(&path) {
                Ok(()) => {}
                Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
                Err(error) => return Err(format!("Could not remove shortcut: {error}")),
            }
            print_json(json!({ "ok": true, "path": path.to_string_lossy() }));
            Ok(())
        }
        "help" | "--help" | "-h" => {
            println!("{}", help());
            Ok(())
        }
        _ => Err(format!(
            "Unknown command: {}\n\n{}",
            arguments.command,
            help()
        )),
    }
}

fn main() -> ExitCode {
    match Arguments::parse().and_then(run) {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => {
            eprintln!("{error}");
            ExitCode::FAILURE
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_named_values() {
        let arguments = Arguments {
            command: "pick-folder".to_string(),
            values: vec![
                "--title".to_string(),
                "Choose data".to_string(),
                "--initial".to_string(),
                "D:\\Socium".to_string(),
            ],
        };
        assert_eq!(arguments.value("--title").unwrap(), "Choose data");
        assert_eq!(arguments.value("--initial").unwrap(), "D:\\Socium");
    }

    #[test]
    fn rejects_missing_named_values() {
        let arguments = Arguments {
            command: "pick-folder".to_string(),
            values: vec!["--title".to_string()],
        };
        assert!(arguments.value("--title").is_err());
    }

    #[test]
    fn reads_runtime_state_without_exposing_token() {
        let root = env::temp_dir().join(format!("socium-helper-test-{}", std::process::id()));
        fs::create_dir_all(&root).unwrap();
        let path = root.join("runtime.json");
        fs::write(
            &path,
            r#"{"webPort":3111,"controlPort":8111,"controlToken":"secret","version":"1.1.0"}"#,
        )
        .unwrap();
        let state = read_runtime_state(&path).unwrap();
        assert_eq!(state.web_port, 3111);
        assert_eq!(state.control_port, 8111);
        assert_eq!(state.version, "1.1.0");
        fs::remove_dir_all(root).unwrap();
    }
}
