use proc_macro::TokenStream;

/// `#[derive(Answer)]` adds `fn answer() -> u32 { 42 }`.
#[proc_macro_derive(Answer)]
pub fn answer(item: TokenStream) -> TokenStream {
    let s = item.to_string();
    let name = s.split_whitespace().skip_while(|w| *w != "struct").nth(1).unwrap().trim_end_matches(';');
    format!("impl {name} {{ fn answer() -> u32 {{ 42 }} }}").parse().unwrap()
}
