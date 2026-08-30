#lang at-exp racket/base
;; The examples from the "@ Syntax" chapter of the Scribble documentation,
;; every one quoted so this file expands, with definitions between them so
;; the expander oracle holds it too. What is pinned here is the SPAN of every
;; at-form and every form inside one, as Racket's own reader reports them.
(define (before-the-examples) 1)

;; At a glance
(define glance
  (list '@foo{blah blah blah}
        '@foo{blah "blah" (`blah'?)}
        '@foo[1 2]{3 4}
        '@foo[1 2 3 4]
        '@foo[#:width 2]{blah blah}
        '@foo{blah blah
              yada yada}
        '@foo{
           blah blah
           yada yada
         }
        '@foo{bar @baz{3}
              blah}
        '@foo{@b{@u[3] @u{4}}
              blah}
        '@C{while (*(p++))
              *p = '\n';}
        '@{blah blah}
        '@{blah @[3]}
        '@{foo
           bar
           baz}
        '@foo
        '@{blah @foo blah}
        '@{blah @foo: blah}
        '@{blah @|foo|: blah}
        '@foo{(+ 1 2) -> @(+ 1 2)!}
        '@foo{A @"string" escape}
        '@"@"
        '@foo{eli@"@"barzilay.org}
        '@foo{A @"{" begins a block}
        '@C{while (*(p++)) {
              *p = '\n';
            }}
        '@foo|{bar}@{baz}|
        '@foo|{bar |@x{X} baz}|
        '@foo|{bar |@x|{@}| baz}|
        '@foo|--{bar}@|{baz}--|
        '@foo|<<{bar}@|{baz}>>|
        '(define \@email "foo@bar.com")
        '(define |@atchar| #\@)
        '@foo{bar @baz[2 3] {4 5}}))

(define (between-the-sections) 2)

;; The command part
(define command
  (list '@`',@foo{blah}
        '@#`#'#,@foo{blah}
        '@(lambda (x) x){blah}
        '@`(unquote foo){blah}
        '@{foo bar
           baz}
        '@'{foo bar
            baz}
        '@foo{bar @; comment
              baz@;
              blah}
        '@foo{x @y z}
        '@foo{x @(* y 2) z}
        '@{@foo bar}
        '@@foo{bar}{baz}))

;; The datum part
(define datum
  (list '@foo[1 (* 2 3)]{bar}
        '@foo[@bar{...}]{blah}
        '@foo[bar]
        '@foo{bar @f[x] baz}
        '@foo[]{bar}
        '@foo[]
        '@foo
        '@foo{}
        '@foo[#:style 'big]{bar}))

;; The body part
(define body
  (list '@foo{f{o}o}
        '@foo{{{}}{}}
        '@foo{bar}
        '@foo{ bar }
        '@foo[1]{ bar }
        '@foo{a @bar{b} c}
        '@foo{a @bar c}
        '@foo{a @(bar 2) c}
        '@foo{A @"}" marks the end}
        '@foo{The prefix: @"@".}
        '@foo{@"@x{y}" --> (x "y")}
        '@foo|{...}|
        '@foo|{"}" follows "{"}|
        '@foo|{Nesting |{is}| ok}|
        '@foo|{Maze
               |@bar{is}
               Life!}|
        '@t|{In |@i|{sub|@"@"s}| too}|
        '@foo|<<<{@x{foo} |@{bar}|.}>>>|
        '@foo|!!{X |!!@b{Y}...}!!|
        '@foo{foo@bar.}
        '@foo{foo@|bar|.}
        '@foo{foo@3.}
        '@foo{foo@|3|.}
        '@foo{foo@|(f 1)|{bar}}
        '@foo{foo@|bar|[1]{baz}}
        '@foo{x@"y"z}
        '@foo{x@|"y"|z}
        '@foo{x@|1 (+ 2 3) 4|y}
        '@foo{x@|*
                *|y}
        '@foo{Alice@||Bob@|
              |Carol}
        '@|{blah}|
        '@foo{First line@;{there is still a
                           newline here;}
              Second line}
        '@foo{A long @;
              single-@;
              string arg.}
        '@foo{
           @|| bar @||
           @|| baz}))

;; `@` where it is NOT a command: inside identifiers and strings.
(define x@y "a@b")
(define (after-the-examples) x@y)

(provide before-the-examples between-the-sections after-the-examples
         glance command datum body x@y)
