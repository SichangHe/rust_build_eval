use pm::Answer;
include!(concat!(env!("OUT_DIR"), "/gen.rs"));

#[derive(Answer)]
struct S;

#[inline(never)]
fn boom(n: u32) -> u32 {
    if n > 100 { panic!("boom {n}") }
    n + S::answer() + GEN
}

fn main() {
    let n: u32 = std::env::args().nth(1).map_or(1, |a| a.parse().unwrap());
    println!("{}", boom(n));
    let t = std::thread::spawn(|| std::time::Instant::now().elapsed().as_nanos() > 0);
    assert!(t.join().unwrap());
}

#[cfg(test)]
mod tests {
    #[test]
    fn works() { assert_eq!(super::boom(1), 1 + 42 + 7); }
    #[test]
    #[should_panic(expected = "boom 101")]
    fn panics() { super::boom(101); }
}
