#lang racket/base
;; Every form here is something that LOOKS like a definition and is not. The
;; expander agrees none of these bind a module-level name, so any of them
;; appearing in the index is a fabrication.

(define live-anchor 1)          ; non-vacuity: the guards must not eat the file

#;(define sexp-commented 3)     ; #; is how Racketeers disable code

'(define quoted-x 1)
`(define quasiquoted-x 2)
#'(define syntaxed-x 3)

(let ([let-bound-x 1] [let-bound-y 2]) (+ let-bound-x let-bound-y))

;; Shape from racket/interactive.rkt: an internal define inside a conditional
;; body. Not requirable from this module.
(when (> 2 1)
  (define conditional-internal 5)
  (void conditional-internal))

;; Shape from racket/private/dict.rkt: a define inside a nested clause of a
;; macro invocation. Also not a module-level binding.
(define (outer-with-helper q)
  (define (nested-helper r) r)
  (nested-helper q))

(provide live-anchor outer-with-helper)

;; Shape from racket/set.rkt's contract combinators: a macro invocation whose
;; body holds `define`s. Those are internal definitions and not importable, so
;; the walker must not descend into a form it does not recognise. Losing that
;; guard fabricated cmp/c, elem/c, equal-key/c, kind/c and lazy? on the real
;; corpus while every test stayed green.
(define-syntax-rule (with-locals body ...)
  (let () body ... (void)))

(with-locals
  (define macro-body-local 1)
  (define (macro-body-fn x) x))
