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
