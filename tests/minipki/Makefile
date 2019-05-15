
DOMAIN = volatildap.org

export DOMAIN

# Main paths
ROOT_CAFILE = ca-$(DOMAIN).crt
ROOT_TEMPKEY = ca-$(DOMAIN).key
INTERM_CRT = interm-$(DOMAIN).crt
INTERM_CSR = interm-$(DOMAIN).csr
INTERM_KEY = interm-$(DOMAIN).key

OPENSSL_CA = openssl-ca-$(DOMAIN).cnf

# Certificate validity (same for every file)
CERT_DAYS = 3650



default: bootstrap

bootstrap: $(INTERM_CRT)

test-cert: localhost.$(DOMAIN).crt

.PHONY: default test-cert

# Generate root CA, intermediate csr, sign intermediate.
$(OPENSSL_CA): openssl-ca.cnf.in
	cat $< | envsubst > $@

$(ROOT_CAFILE) $(ROOT_TEMPKEY): $(OPENSSL_CA)
	openssl req -config $< -x509 -extensions root_certificate -out $(ROOT_CAFILE) -keyout $(ROOT_TEMPKEY) \
	    -days $(CERT_DAYS) -nodes

$(INTERM_CSR) $(INTERM_KEY): $(OPENSSL_CA)
	openssl req -config $< -newkey rsa -nodes -out $(INTERM_CSR) -keyout $(INTERM_KEY)

$(INTERM_CRT): $(ROOT_CAFILE) $(INTERM_CSR) $(OPENSSL_CA)
	echo '01' > $<.srl
	openssl x509 -extfile $(OPENSSL_CA) -extensions interm_ca -req -days $(CERT_DAYS) \
	    -in $(INTERM_CSR) -out $@ \
	    -CA $(ROOT_CAFILE) -CAkey $(ROOT_TEMPKEY) -CAserial $<.srl
	rm $(ROOT_TEMPKEY)
	rm $<.srl

# Generate all forms of leaf certificates

%.csr %.key: openssl-%.cnf
	openssl req -config $< -newkey rsa -nodes -out $*.csr -keyout $*.key

%.crt: %.csr $(INTERM_CRT) $(INTERM_KEY) openssl-%.cnf
	echo '01' > $*.srl
	openssl x509 -extfile openssl-$*.cnf -extensions leaf_cert -req -days $(CERT_DAYS) \
	    -in $< -out $@ \
	    -CA $(INTERM_CRT) -CAkey $(INTERM_KEY) -CAserial $*.srl
	rm $*.srl

openssl-%.cnf: openssl-leaf.cnf.in
	cat $< | FQDN=$* envsubst > $@


clean:
	-rm leaf-*

.PHONY: clean


hard-reset: clean
	-rm $(ROOT_CAFILE) $(INTERM_KEY) $(INTERM_CRT) *.cnf *.csr *.srl

.PHONY: hard-reset
