#lang racket/base
;; The honest gap, isolated. `define-constants` is the shape of
;; racket/fasl.rkt's own macro (49 names) and racket/list.rkt's
;; `(define-lgetter second 2)` (12 names): a macro invocation that DEFINES.
;;
;; The names below are `syntax-original?` -- a human typed them -- but no
;; `define` form exists for a static parser to match. They are the irreducible
;; part of the coverage gap, and this fixture exists so that gap stays visible
;; and attributable rather than becoming a mystery.

(require (for-syntax racket/base))

(define-syntax (define-constants stx)
  (syntax-case stx ()
    [(_ name ...)
     (with-syntax ([(i ...) (for/list ([n (syntax->list #'(name ...))]
                                       [k (in-naturals)])
                              k)])
       #'(begin (define name i) ...))]))

(define-constants fasl-box-type fasl-char-type fasl-eof-type)

(define (reachable-by-static-parsing x) x)

(provide fasl-box-type fasl-char-type fasl-eof-type reachable-by-static-parsing)
