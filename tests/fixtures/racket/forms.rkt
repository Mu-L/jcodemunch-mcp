#lang racket/base
;; Binding forms that yielded `(no symbols)`, or the wrong kind, or a name
;; Racket does not bind, before the gen-5 extractor. One instance of each; the
;; frozen oracle beside this file is what Racket's own expander says.
(require racket/contract racket/match racket/generic racket/stxparam
         racket/performance-hint racket/unit syntax/parse syntax/parse/define
         rackunit (for-syntax racket/base))

;; racket/performance-hint: `begin` with a hint. Hid sqr/sgn/conjugate.
(begin-encourage-inline
  (define (inlined-sqr z) (* z z))
  (define inlined-pi 3))

;; The old supertype header: a LIST in the name slot.
(struct parent (p))
(define-struct (child parent) (a b))

;; Binds gen:stack, stack?, stack/c and each method -- and NOT `stack`.
(define-generics stack
  (stack-push stack v)
  (stack-pop stack))

;; Binds app-logger and log-app-<level>, and NOT `app`.
(define-logger app)

;; The value is at children[3], after the contract.
(define/contract contracted-handler (-> any/c any/c) (lambda (x) x))

;; Lambda-shaped macros.
(define matcher (match-lambda [_ 1]))

(define-syntax-parse-rule (my-or a b) (or a b))
(define-syntax-parameter it #f)
(define-match-expander pt (syntax-rules () [(_ a b) (cons a b)]))
(define-sequence-syntax in-things (lambda () #'in-list) (lambda (stx) #f))
(define-syntax-class num (pattern n:number))
(define-inline (fast-id x) x)
(define-check (check-foo x) (void))
(define-unit unit@ (import) (export) (define (unit-internal) 1))

;; Two blocks, one submodule.
(module+ test
  (define (t1) 1))
(define (between) 2)
(module+ test
  (define (t2) 2))

(provide inlined-sqr inlined-pi child contracted-handler matcher my-or
         fast-id check-foo unit@ between)
