//! Shapes where a bare NAME is not a definition's identity.
//!
//! ⚠⚠ Every definition here shares its name with another in this same file.
//! That is the point. A comparison that keys on bare names in a SET reports
//! this file as perfectly extracted no matter how many of these collapse into
//! one another -- proven 2026-08-27 by deleting the second symbol of every
//! duplicated name in the fixture set and watching `extra` and `missing` not
//! move. ripgrep's `crates/core/flags/defs.rs` repeats `is_switch` 108 times.

pub struct Alpha;
pub struct Beta;

impl Alpha {
    /// Same name, different owner. `Alpha.new` vs `Beta.new`.
    pub fn new() -> Self {
        Alpha
    }
    /// ⚠ A `const` inside an impl. `_constant_symbol` hardcodes
    /// `qualified_name = name` and takes no parent, so this used to come out
    /// as a bare `LIMIT` -- 35 of these in ripgrep.
    const LIMIT: usize = 4;
}

impl Beta {
    pub fn new() -> Self {
        Beta
    }
    const LIMIT: usize = 8;
}

pub trait Carrier {
    /// ⚠ `type Carried;` is an `associated_type`, NOT the `type_item` an impl
    /// writes. Same shape as `function_signature_item`: the half of the
    /// contract an implementor MUST supply was the half we could not find.
    type Carried;

    fn carry(&self) -> Self::Carried;
}

impl Carrier for Alpha {
    type Carried = u32;
    fn carry(&self) -> u32 {
        Alpha::LIMIT as u32
    }
}

impl Carrier for Beta {
    type Carried = u64;
    fn carry(&self) -> u64 {
        Beta::LIMIT as u64
    }
}

/// ⚠ Generic and lifetime parameters belong to the impl, not to the name.
/// `Holder<'a, T>` owns `get`, so the owner is `Holder`.
pub struct Holder<'a, T> {
    pub inner: &'a T,
}

impl<'a, T> Holder<'a, T> {
    pub fn get(&self) -> &'a T {
        self.inner
    }
}

/// ⚠ A self type with no path at all. The oracle renders it from its tokens;
/// returning nothing here would file `carry` under a bare name, which is the
/// collision the whole field exists to remove.
impl Carrier for (u8, u8) {
    type Carried = u8;
    fn carry(&self) -> u8 {
        self.0
    }
}

/// ⚠ An item defined inside a function BODY. Rust cannot name it from
/// outside, so neither spelling is "the" path -- but `outer_helper.helper`
/// says where it lives and a bare `helper` collides with every other one.
pub fn outer_helper() -> usize {
    fn helper() -> usize {
        1
    }
    const SCALE: usize = 3;
    helper() * SCALE
}
