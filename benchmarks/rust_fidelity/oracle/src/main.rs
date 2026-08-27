//! Ground truth for Rust symbol extraction: Rust's own parser.
//!
//! Emits one record per DEFINITION with name, kind and the 1-based line of the
//! IDENTIFIER.
//!
//! ⚠⚠ Built on `syn::visit::Visit`, NOT a hand-rolled walk, and that is a
//! correctness decision rather than a style one. A hand-rolled walker only sees
//! the places its author remembered to look, and every place it forgets makes
//! the EXTRACTOR look wrong: a definition the oracle cannot reach is scored as
//! a fabrication. Two rounds of that happened here before this rewrite --
//! first function bodies (35 phantom "extras"), then `const`s inside a `for`
//! body and a `match` arm (2 more). `Visit` recurses through expressions,
//! blocks, arms and closures by default, so the blind spots have to be added
//! deliberately instead of arrived at by omission.
//!
//! ⚠⚠ The IDENTIFIER's span, never the item's. `syn`'s `Item::span()` starts at
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
//! direction, and no bucket should be read as covering them.
use proc_macro2::Span;
use std::collections::BTreeSet;
use syn::visit::Visit;

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

struct Collector {
    file: String,
    out: BTreeSet<Def>,
}

impl Collector {
    fn push(&mut self, name: String, kind: &'static str, line: usize) {
        self.out.insert(Def { file: self.file.clone(), name, kind, line });
    }
}

impl<'ast> Visit<'ast> for Collector {
    fn visit_item_fn(&mut self, i: &'ast syn::ItemFn) {
        self.push(i.sig.ident.to_string(), "function", line_of(i.sig.ident.span()));
        syn::visit::visit_item_fn(self, i);
    }

    fn visit_item_struct(&mut self, i: &'ast syn::ItemStruct) {
        self.push(i.ident.to_string(), "struct", line_of(i.ident.span()));
        syn::visit::visit_item_struct(self, i);
    }

    fn visit_item_enum(&mut self, i: &'ast syn::ItemEnum) {
        self.push(i.ident.to_string(), "enum", line_of(i.ident.span()));
        syn::visit::visit_item_enum(self, i);
    }

    fn visit_item_union(&mut self, i: &'ast syn::ItemUnion) {
        self.push(i.ident.to_string(), "union", line_of(i.ident.span()));
        syn::visit::visit_item_union(self, i);
    }

    fn visit_item_trait(&mut self, i: &'ast syn::ItemTrait) {
        self.push(i.ident.to_string(), "trait", line_of(i.ident.span()));
        syn::visit::visit_item_trait(self, i);
    }

    fn visit_item_type(&mut self, i: &'ast syn::ItemType) {
        self.push(i.ident.to_string(), "type", line_of(i.ident.span()));
        syn::visit::visit_item_type(self, i);
    }

    fn visit_item_const(&mut self, i: &'ast syn::ItemConst) {
        self.push(i.ident.to_string(), "constant", line_of(i.ident.span()));
        syn::visit::visit_item_const(self, i);
    }

    fn visit_item_static(&mut self, i: &'ast syn::ItemStatic) {
        self.push(i.ident.to_string(), "constant", line_of(i.ident.span()));
        syn::visit::visit_item_static(self, i);
    }

    fn visit_item_mod(&mut self, i: &'ast syn::ItemMod) {
        self.push(i.ident.to_string(), "module", line_of(i.ident.span()));
        syn::visit::visit_item_mod(self, i);
    }

    fn visit_item_macro(&mut self, i: &'ast syn::ItemMacro) {
        // `macro_rules! name { .. }` DEFINES. A macro CALL has no ident.
        if let Some(id) = &i.ident {
            self.push(id.to_string(), "macro", line_of(id.span()));
        }
        syn::visit::visit_item_macro(self, i);
    }

    fn visit_impl_item_fn(&mut self, i: &'ast syn::ImplItemFn) {
        self.push(i.sig.ident.to_string(), "method", line_of(i.sig.ident.span()));
        syn::visit::visit_impl_item_fn(self, i);
    }

    fn visit_impl_item_const(&mut self, i: &'ast syn::ImplItemConst) {
        self.push(i.ident.to_string(), "constant", line_of(i.ident.span()));
        syn::visit::visit_impl_item_const(self, i);
    }

    fn visit_impl_item_type(&mut self, i: &'ast syn::ImplItemType) {
        self.push(i.ident.to_string(), "type", line_of(i.ident.span()));
        syn::visit::visit_impl_item_type(self, i);
    }

    /// ⚠ Covers BOTH halves of a trait method: one with a default body and one
    /// that is a signature only (`fn required(&self) -> u32;`). The second was
    /// a real extraction gap -- the API surface an implementor must provide was
    /// exactly the half jCodeMunch could not find.
    fn visit_trait_item_fn(&mut self, i: &'ast syn::TraitItemFn) {
        self.push(i.sig.ident.to_string(), "method", line_of(i.sig.ident.span()));
        syn::visit::visit_trait_item_fn(self, i);
    }

    fn visit_trait_item_const(&mut self, i: &'ast syn::TraitItemConst) {
        self.push(i.ident.to_string(), "constant", line_of(i.ident.span()));
        syn::visit::visit_trait_item_const(self, i);
    }

    fn visit_trait_item_type(&mut self, i: &'ast syn::TraitItemType) {
        self.push(i.ident.to_string(), "type", line_of(i.ident.span()));
        syn::visit::visit_trait_item_type(self, i);
    }

    /// ⚠⚠ Deliberately NOT visited as definitions: struct fields, enum
    /// variants, `let` bindings and closures. None of them binds a name another
    /// module can reach, and emitting them would make the `extra` gate reject
    /// correct extraction. Each omission is a decision recorded here; a
    /// hand-rolled walker records the same omissions as silence.
    fn visit_field(&mut self, i: &'ast syn::Field) {
        syn::visit::visit_field(self, i);
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
        if p.extension().map(|x| x != "rs").unwrap_or(true) {
            continue;
        }
        if p.components().any(|c| c.as_os_str() == "target") {
            continue;
        }
        let rel = p
            .strip_prefix(&root)
            .unwrap()
            .to_string_lossy()
            .replace(std::path::MAIN_SEPARATOR, "/");
        let src = match std::fs::read_to_string(p) {
            Ok(s) => s,
            Err(_) => {
                failed += 1;
                failed_files.push(rel);
                continue;
            }
        };
        match syn::parse_file(&src) {
            Ok(f) => {
                parsed += 1;
                let mut c = Collector { file: rel, out: BTreeSet::new() };
                c.visit_file(&f);
                out.extend(c.out);
            }
            Err(_) => {
                failed += 1;
                failed_files.push(rel);
            }
        }
    }
    let recs: Vec<_> = out
        .iter()
        .map(|d| {
            serde_json::json!({
                "file": d.file, "name": d.name, "kind": d.kind, "line": d.line
            })
        })
        .collect();
    let doc = serde_json::json!({
        "files_parsed": parsed, "files_failed": failed,
        "failed_files": failed_files, "defs": recs,
    });
    println!("{}", serde_json::to_string(&doc).unwrap());
}
