fn main() {
    println!("cargo:rerun-if-env-changed=SOCIUM_BUNDLE_PATH");
    println!("cargo:rerun-if-env-changed=SOCIUM_BUNDLE_SHA256");
    println!("cargo:rerun-if-env-changed=SOCIUM_RELEASE_TARGET");
    println!("cargo:rerun-if-env-changed=SOCIUM_RELEASE_VERSION");
    println!("cargo:rerun-if-env-changed=SOCIUM_RELEASE_MANIFEST");
    #[cfg(target_os = "windows")]
    {
        let mut resource = winresource::WindowsResource::new();
        resource.set_icon("../../src/app/favicon.ico");
        resource.set("ProductName", "Socium");
        resource.set("FileDescription", "Socium Setup");
        resource.set("LegalCopyright", "Socium contributors");
        resource.compile().expect("could not compile Windows installer resources");
    }
}
