#lang at-exp racket/base
;; at-exp text bodies carrying the four characters that are prose to Racket's
;; reader and tokens to tree-sitter: `;` (comment), `"` (string), `#` and
;; `|` (reader prefixes). Before the #lang gate, the `"` alone swallowed every
;; definition after it in the file, and error recovery re-parented internal
;; defines to module level. The raw bytes still fail the grammar -- the test
;; asserts that -- and the walker must find every definition regardless.
(require racket/list)

(define (before-the-bodies) 1)

(define (step-one)
  @list{Thanks; you are done})

(define (step-two)
  @list{He said "hi" and left})

(define (step-three)
  (define (internal-helper) 3)
  @list{Item #1 of 3 | done @|internal-helper|})

(define (after-the-bodies) 4)

(provide before-the-bodies step-one step-two step-three after-the-bodies)
