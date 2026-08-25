#lang racket/base
;; Shapes drawn from real Racket library code. Each one is a form the
;; extractor dispatches on; the frozen oracle output beside this file is what
;; Racket's own expander says about it.
(require racket/class)

;; Greets a person by name.
(define (greet name) (string-append "hi " name))

(define greeting "hello")

(define handler (lambda (x) x))

(define ((adder a) b) (+ a b))

(struct point (x y) #:transparent)

;; Shape from racket/private/class-internal.rkt: a struct with a supertype.
(struct point3 point (z) #:transparent)

(define-values (quotient-part remainder-part) (quotient/remainder 7 2))

(define-syntax-rule (swap-in-place! a b)
  (let ([tmp a]) (set! a b) (set! b tmp)))

(define shape%
  (class object%
    (super-new)
    (define/public (area) 4)
    (define/private (secret) 1)))

(module+ test
  (define (test-helper x) x))

(provide greet greeting handler adder point point3 swap-in-place! shape%)
