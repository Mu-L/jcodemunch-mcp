//! Ordinary Rust definitions. If any of these go missing, extraction broke in
//! a way no amount of macro cleverness explains.

use std::fmt;

pub const MAX_DEPTH: usize = 32;
static GREETING: &str = "hello";

pub struct Config {
    pub depth: usize,
}

pub enum Mode {
    Fast,
    Careful,
}

pub union Raw {
    int: u32,
    float: f32,
}

pub type Result2<T> = std::result::Result<T, Error>;

pub struct Error;

pub trait Render {
    /// A required method: signature only, NO default body.
    fn render(&self) -> String;

    /// A provided method: has a body.
    fn render_twice(&self) -> String {
        let once = self.render();
        format!("{once}{once}")
    }
}

impl Render for Config {
    fn render(&self) -> String {
        format!("depth={}", self.depth)
    }
}

impl Config {
    pub fn new(depth: usize) -> Self {
        Config { depth }
    }

    fn clamp(&self) -> usize {
        self.depth.min(MAX_DEPTH)
    }
}

impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "error")
    }
}

/// ⚠ A trait with a required method and NO implementor in this file.
///
/// Deliberate: `Render::render` is a required method too, but an `impl Render
/// for Config` below defines the SAME NAME, so a name-keyed gap check sees
/// `render` present and the missing signature is masked. This trait has no
/// impl, so `probe_signature_only` appears exactly once -- as a signature --
/// and its absence is detectable.
pub trait Probe {
    fn probe_signature_only(&self) -> u32;
}

pub fn top_level(x: u32) -> u32 {
    x + 1
}

pub mod inner {
    pub fn nested_in_module() -> &'static str {
        super::GREETING
    }
}
