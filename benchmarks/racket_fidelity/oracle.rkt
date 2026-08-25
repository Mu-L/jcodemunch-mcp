#lang racket/base
;; Ground-truth oracle for the Racket extraction-fidelity benchmark.
;;
;; Racket's own expander is the authority. `expand` runs the full macro layer,
;; so every binding a module really defines shows up as `define-values` /
;; `define-syntaxes` in the expanded form -- including the ones no static
;; parser can see, because their names were introduced by a macro.
;;
;; `syntax-original?` is what makes the comparison meaningful: it separates
;; names a HUMAN TYPED from names a MACRO INTRODUCED. Only the first group is
;; something a static parser could reasonably have found, so only the first
;; group belongs in a coverage number.
;;
;; `module->exports` adds the surface a CONSUMER sees, which is a different
;; question -- it is post-`rename-out`, so it answers "what can be called"
;; rather than "what was defined".
;;
;; Usage:  racket oracle.rkt <file.rkt> ...      -> one JSON object per line
;;
;; ⚠ The export probe uses `dynamic-require`, which INSTANTIATES the module.
;; Point this at libraries, not at scripts with side effects.

(require racket/list json)

(define (expand-file path)
  (define dir (let-values ([(d f r) (split-path (path->complete-path path))]) d))
  (define stx
    (parameterize ([read-accept-reader #t]
                   [read-accept-lang #t]
                   [current-load-relative-directory dir])
      (with-input-from-file path
        (lambda ()
          (port-count-lines! (current-input-port))
          (read-syntax path)))))
  (parameterize ([current-namespace (make-base-namespace)]
                 [current-load-relative-directory dir])
    (expand stx)))

;; Walk expanded syntax collecting every module-level binding form.
(define (collect-definitions stx)
  (define out '())
  (let walk ([s stx])
    (define e (syntax-e s))
    (when (pair? e)
      (define head (car e))
      (define hd (and (identifier? head) (syntax-e head)))
      ;; A submodule is a real, requirable entity -- (require (submod "m.rkt"
      ;; reader)) -- but it is NOT a binding in the enclosing namespace, so the
      ;; define-values walk alone never sees it. Without this, a parser that
      ;; correctly reports `(module reader ...)` is scored as inventing a name.
      (when (and (memq hd '(module module*)) (pair? (cdr e))
                 (identifier? (cadr e)))
        (set! out
              (cons (hasheq 'name (symbol->string (syntax-e (cadr e)))
                            'line (or (syntax-line (cadr e)) 'null)
                            'kind "module"
                            'from_source (and (syntax-original? (cadr e)) #t))
                    out)))
      (when (memq hd '(define-values define-syntaxes))
        (define parts (syntax->list s))
        (define ids (and parts (>= (length parts) 2) (syntax->list (cadr parts))))
        ;; `define-syntaxes` can bind through a non-identifier form in the
        ;; binding position (racket/splicing.rkt does), and syntax-e then hands
        ;; back a LIST. Guard, or the oracle crashes on the file and the
        ;; benchmark quietly loses it from the denominator.
        (for ([i (in-list (or ids '()))] #:when (identifier? i))
          (set! out
                (cons (hasheq 'name (symbol->string (syntax-e i))
                              'line (or (syntax-line i) 'null)
                              'kind (if (eq? hd 'define-syntaxes) "syntax" "value")
                              'from_source (and (syntax-original? i) #t))
                      out))))
      (let inner ([x e])
        (cond [(pair? x) (when (syntax? (car x)) (walk (car x))) (inner (cdr x))]
              [(syntax? x) (walk x)]
              [else (void)]))))
  (reverse out))

;; The consumer-visible surface: post-rename-out, post-struct-out.
;; `procedure?` on the instantiated value is the only honest evidence for
;; whether a binding is callable, which is what the parser's
;; lambda-versus-value guess is really claiming.
(define (collect-exports path)
  (define mp `(file ,(path->string (path->complete-path path))))
  (with-handlers ([exn:fail? (lambda (e) '())])
    (dynamic-require mp (void))
    (define-values (vals stxs) (module->exports mp))
    (append
     (for*/list ([phase (in-list vals)] [entry (in-list (cdr phase))])
       (define nm (car entry))
       (hasheq 'name (symbol->string nm)
               'kind "value"
               'procedure
               (with-handlers ([exn:fail? (lambda (e) 'null)])
                 (and (procedure? (dynamic-require mp nm)) #t))))
     (for*/list ([phase (in-list stxs)] [entry (in-list (cdr phase))])
       (hasheq 'name (symbol->string (car entry))
               'kind "syntax"
               'procedure 'null)))))

(for ([path (in-vector (current-command-line-arguments))])
  (define result
    (with-handlers ([exn:fail?
                     (lambda (e) (hasheq 'file path 'error (exn-message e)))])
      (hasheq 'file path
              'definitions (collect-definitions (expand-file path))
              'exports (collect-exports path))))
  (write-json result)
  (newline)
  (flush-output))
