#lang racket/base
;; Reader-level oracle: what Racket's OWN reader sees in a file, as a tree of
;; (type, byte-start, byte-span) triples.
;;
;; `read-syntax` is run with `read-accept-reader`, so a `#lang` line selects
;; the language's reader exactly as `racket file.rkt` would -- at-exp, Scribble,
;; a project's own `#lang` -- and the result is the module form, unwrapped here
;; to its body. Line counting is deliberately OFF: without it `syntax-position`
;; counts BYTES (measured: a "λ" string spans 4), which is what the Python
;; reader reports, so no character-to-byte conversion sits between the two.
;;
;; Every syntax object becomes one node. Lists produced by a quote PREFIX
;; (`'x`, `#'x`, `,@x` ...) are typed by the prefix, not as a list, because
;; that is the shape tree-sitter-racket gives and the walker expects; the
;; discriminator is the head identifier's span, which equals the prefix's
;; length and never the spelled-out name's. An at-exp form carries its
;; `'scribble` property as a flag so the comparison can drop the strings
;; INSIDE it (the at-exp reader splits and merges text in ways the Python
;; reader does not model and the walker never reads).
;;
;; One JSON object per file on stdout: {"file": ..., "nodes": [[type pos span
;; at?] ...]} or {"file": ..., "error": message}. Positions are 1-based.
(require racket/path racket/list racket/extflonum json)

(define quote-heads
  (hash 'quote 1 'quasiquote 1 'unquote 1 'unquote-splicing 2
        'syntax 2 'quasisyntax 2 'unsyntax 2 'unsyntax-splicing 3))

(define (quote-prefix-type stx)
  ;; (quote x) written with a PREFIX, else #f.
  (define e (syntax-e stx))
  (and (pair? e)
       (let ([items (syntax->list stx)])
         (and items (= 2 (length items))
              (identifier? (car items))
              (let ([h (syntax-e (car items))])
                (and (hash-ref quote-heads h #f)
                     (eqv? (syntax-span (car items)) (hash-ref quote-heads h))
                     (regexp-replace* #rx"-" (symbol->string h) "_")))))))

(define (at-form? stx)
  (define p (syntax-property stx 'scribble))
  (and (pair? p) (eq? (car p) 'form) (or (cadr p) (caddr p)) #t))

(define (emit stx out)
  (define e (syntax-e stx))
  (define pos (syntax-position stx))
  (define span (syntax-span stx))
  (define (push type . kids)
    (set-box! out (cons (list type pos span (at-form? stx)) (unbox out)))
    (for ([k (in-list kids)]) (emit k out)))
  (define (pair-items e)
    ;; A dotted tail is ONE child: `(a . ,b)` reads as (a unquote b), but the
    ;; reader wraps the `,b` as its own syntax object in cdr position, and
    ;; splicing it into the parent would lose that node (and show a bare `,`
    ;; symbol where the Python reader has an `unquote`).
    (let loop ([e e] [acc '()])
      (cond [(pair? e) (loop (cdr e) (cons (car e) acc))]
            [(null? e) (reverse acc)]
            [(syntax? e) (reverse (cons e acc))]
            [else (reverse acc)])))
  (cond
    [(or (pair? e) (null? e))
     (define qt (quote-prefix-type stx))
     (if qt
         (push qt (cadr (syntax->list stx)))
         (apply push "list" (pair-items e)))]
    [(symbol? e) (push "symbol")]
    [(keyword? e) (push "keyword")]
    [(string? e) (push "string")]
    [(bytes? e) (push "byte_string")]
    [(char? e) (push "character")]
    [(boolean? e) (push "boolean")]
    [(or (number? e) (extflonum? e)) (push "number")]
    ;; `#3(a)` fills the vector by REPEATING the last element, so the syntax
    ;; vector holds the same object three times; one element per source datum.
    [(vector? e) (apply push "vector" (remove-duplicates (vector->list e) eq?))]
    [(box? e) (push "box" (unbox e))]
    [(hash? e) (push "hash")]
    [(prefab-struct-key e) (push "structure")]
    [(or (regexp? e) (byte-regexp? e)) (push "regex")]
    [else (push "other")]))

(define (module-body stx)
  ;; (module name lang (#%module-begin form ...)) or (module name lang form ...)
  (define parts (syntax->list stx))
  (cond
    [(and parts (>= (length parts) 3) (identifier? (car parts))
          (eq? 'module (syntax-e (car parts))))
     (define body (cdddr parts))
     (if (and (= 1 (length body))
              (let ([b (syntax-e (car body))])
                (and (pair? b) (identifier? (car b))
                     (regexp-match? #rx"module-begin$" (symbol->string (syntax-e (car b)))))))
         (cdr (syntax->list (car body)))
         body)]
    [else (list stx)]))

(define (has-lang? path)
  (call-with-input-file path
    (lambda (in)
      ;; Comment forms may precede `#lang`: `;` lines, `#| |#` blocks, shebangs.
      (regexp-match? #px#"^(?:[ \t\r\n]|;[^\n]*\n|#\\|(?:[^|]|\\|(?!#))*\\|#|#![^\n]*\n)*#(?:lang |!)"
                     (peek-bytes 4096 0 in)))))

(for ([path (in-vector (current-command-line-arguments))])
  (define out (box '()))
  (define res
    (with-handlers ([exn:fail? (lambda (e) (hasheq 'file path 'error (exn-message e)))])
      (parameterize ([read-accept-reader #t] [read-accept-lang #t]
                     [current-load-relative-directory (path-only (path->complete-path path))])
        (call-with-input-file path
          (lambda (in)
            (let loop ()
              (define stx (read-syntax path in))
              (unless (eof-object? stx)
                (for ([f (in-list (if (has-lang? path) (module-body stx) (list stx)))])
                  (emit f out))
                (loop))))))
      (hasheq 'file path 'nodes (reverse (unbox out)))))
  (write-json res) (newline) (flush-output))
