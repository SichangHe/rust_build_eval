fn main() {
    let out = std::env::var("OUT_DIR").unwrap();
    std::fs::write(format!("{out}/gen.rs"), "pub const GEN: u32 = 7;").unwrap();
}
