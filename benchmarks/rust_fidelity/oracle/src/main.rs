//! Ground truth for Rust symbol extraction: Rust's own parser.
//!
//! Emits one record per DEFINITION with name, kind and the 1-based line of the
//! IDENTIFIER.
//!
//! ⚠⚠ The identifier's span, never the item's. `syn`'s `Item::span()` starts at
//! the first doc comment or outer attribute, so an item's span line is where
//! its DOCUMENTATION begins. Measuring against that scored jCodeMunch at 40.4%
//! when the real figure was 95.4%, and every delta was one-sided -- jcm was
//! never earlier, which is the signature of an oracle artifact rather than an
//! extractor bug.
//!
//! ⚠⚠ THIS IS A PARSER, NOT AN EXPANDER, and that is the honest ceiling of the
//! whole harness. Racket's oracle expands, so it sees macro-introduced names.
//! `syn` does not expand, so an item produced by a `macro_rules!` invocation is
//! invisible to BOTH sides. Such names are not scored here, in either
//! direction, and no bucket below should be read as covering them.
use proc_macro2::Span;
use std::collections::BTreeSet;

#[derive(PartialEq, Eq, PartialOrd, Ord)]
struct Def {
    file: String,
    name: String,
    kind: &'static str,
    line: usize,
}

fn line_of(s: Span) -> usize {
    s.start().line
}

fn push(out: &mut BTreeSet<Def>, file: &str, name: String, kind: &'static str, line: usize) {
    out.insert(Def { file: file.to_string(), name, kind, line });
}

/// Walk a block's statements for nested item definitions.
///
/// ⚠ Rust allows items inside function bodies, and real code uses it heavily:
/// the `#[cfg(windows)] fn imp(..) / #[cfg(not(windows))] fn imp(..)` pattern
/// appears 8 times in ripgrep's `pathutil.rs` alone. An oracle that stops at
/// the item level reports every one of them as a FABRICATION by the extractor,
/// which inverts the `extra` gate: real code would fail the build.
fn walk_block(file: &str, block: &syn::Block, out: &mut BTreeSet<Def>) {
    for stmt in &block.stmts {
        if let syn::Stmt::Item(item) = stmt {
            walk_items(file, std::slice::from_ref(item), out);
        }
    }
}

fn walk_items(file: &str, items: &[syn::Item], out: &mut BTreeSet<Def>) {
    for it in items {
        match it {
            syn::Item::Fn(f) => {
                push(out, file, f.sig.ident.to_string(), "function", line_of(f.sig.ident.span()));
                walk_block(file, &f.block, out);
            }
            syn::Item::Struct(s) => push(out, file, s.ident.to_string(), "struct", line_of(s.ident.span())),
            syn::Item::Enum(e) => push(out, file, e.ident.to_string(), "enum", line_of(e.ident.span())),
            syn::Item::Trait(t) => push(out, file, t.ident.to_string(), "trait", line_of(t.ident.span())),
            syn::Item::Union(u) => push(out, file, u.ident.to_string(), "union", line_of(u.ident.span())),
            syn::Item::Type(t) => push(out, file, t.ident.to_string(), "type", line_of(t.ident.span())),
            syn::Item::Const(c) => push(out, file, c.ident.to_string(), "constant", line_of(c.ident.span())),
            syn::Item::Static(s) => push(out, file, s.ident.to_string(), "constant", line_of(s.ident.span())),
            syn::Item::Macro(m) => {
                // `macro_rules! name { .. }` -- a definition. A macro CALL has
                // no ident and defines nothing here.
                if let Some(id) = &m.ident {
                    push(out, file, id.to_string(), "macro", line_of(id.span()));
                }
            }
            syn::Item::Mod(m) => {
                push(out, file, m.ident.to_string(), "module", line_of(m.ident.span()));
                if let Some((_, inner)) = &m.content {
                    walk_items(file, inner, out);
                }
            }
            syn::Item::Impl(im) => {
                for sub in &im.items {
                    match sub {
                        syn::ImplItem::Fn(f) => {
                            push(out, file, f.sig.ident.to_string(), "method", line_of(f.sig.ident.span()));
                            walk_block(file, &f.block, out);
                        }
                        syn::ImplItem::Const(c) => push(out, file, c.ident.to_string(), "constant", line_of(c.ident.span())),
                        syn::ImplItem::Type(t) => push(out, file, t.ident.to_string(), "type", line_of(t.ident.span())),
                        _ => {}
                    }
                }
            }
            _ => {}
        }
        // Trait bodies carry provided methods, which are real definitions.
        if let syn::Item::Trait(t) = it {
            for sub in &t.items {
                match sub {
                    syn::TraitItem::Fn(f) => {
                        push(out, file, f.sig.ident.to_string(), "method", line_of(f.sig.ident.span()));
                        if let Some(b) = &f.default { walk_block(file, b, out); }
                    }
                    syn::TraitItem::Const(c) => push(out, file, c.ident.to_string(), "constant", line_of(c.ident.span())),
                    syn::TraitItem::Type(t2) => push(out, file, t2.ident.to_string(), "type", line_of(t2.ident.span())),
                    _ => {}
                }
            }
        }
    }
}

fn main() {
    let root = std::env::args().nth(1).expect("usage: oracle <dir>");
    let root = std::path::PathBuf::from(root);
    let mut out = BTreeSet::new();
    let (mut parsed, mut failed) = (0usize, 0usize);
    let mut failed_files: Vec<String> = Vec::new();
    for e in walkdir::WalkDir::new(&root).into_iter().filter_map(|e| e.ok()) {
        let p = e.path();
        if p.extension().map(|x| x != "rs").unwrap_or(true) { continue; }
        if p.components().any(|c| c.as_os_str() == "target") { continue; }
        let rel = p.strip_prefix(&root).unwrap().to_string_lossy()
            .replace(std::path::MAIN_SEPARATOR, "/");
        let src = match std::fs::read_to_string(p) {
            Ok(s) => s,
            Err(_) => { failed += 1; failed_files.push(rel); continue }
        };
        match syn::parse_file(&src) {
            Ok(f) => { parsed += 1; walk_items(&rel, &f.items, &mut out); }
            Err(_) => { failed += 1; failed_files.push(rel); }
        }
    }
    let recs: Vec<_> = out.iter().map(|d| serde_json::json!({
        "file": d.file, "name": d.name, "kind": d.kind, "line": d.line
    })).collect();
    let doc = serde_json::json!({
        "files_parsed": parsed, "files_failed": failed,
        "failed_files": failed_files, "defs": recs,
    });
    println!("{}", serde_json::to_string(&doc).unwrap());
}
