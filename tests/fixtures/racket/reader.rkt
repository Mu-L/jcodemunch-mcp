#lang racket/base
;; One instance of every default-reader form, so the frozen reader oracle
;; pins the SPAN of each. Everything is data (quoted) except the definitions,
;; so the expander oracle can hold this file too.
#| a block
   #| nested |# comment |#
#;(a discarded datum)
(define (reader-basics x #:kw [y 2] . rest)
  (list ''q '`(qq ,uq ,@uqs) '#'stx '#`qstx '#,ustx '#,@ustxs x y rest))

(define reader-atoms
  '("str" #"bytes" #\a #\space #\u3BB #\λ #\( 42 1.5 1/2 #x1F #xFF #e1.0 #i5 +inf.0 -nan.0 1+2i 1@2
    #t #f #true #false #:kw |sym bol| foo|bar|baz a\ b #%app .5 5. 1e3 1+ - ... .foo #cs Apple))

(define reader-compound
  '(#(1 2) #3(a) #hash((a . 1)) #hasheq() #hasheqv((k . v)) #hashalw() #s(pt 1 2) #&box
    #rx"re" #px"px" #rx#"b" #px#"c" (a . b) (a . < . b) {x} [y] ()))

(define reader-here-string #<<EOS
here; "string" with #| every |# hazard @foo{x}
EOS
  )

(define reader-shebang-follows 1)
#! /usr/bin/env racket
#!/bin/sh continues \
  onto this line
(define reader-after-shebang 2)

(provide reader-basics reader-atoms reader-compound reader-here-string
         reader-shebang-follows reader-after-shebang)
