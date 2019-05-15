# mini-pki

This mini PKI is intended for local development.

It is able to generate valid certificates, with proper X509 extensions, using a root CA that can **safely** be
added to the operating system trust store:
* The root CA's signing key has been removed (it can't be used to sign new intermediate certificates)
* It is restricted only to the local development domain


## Usage

First, run `make bootstrap`.
This will generate a root CA and the associated intermediate.

Afterwards, simply run `make leaf-foo.example.org.crt` to generate a certificate for that domain.

## Bootstrap workflow

On first run (or when changing the development domain name), the stack will:
* Generate a self-signed root CA, restricted to the development domain
* Generate an intermediary CA, restricted to the development domain
* Signed the intermediary CA with the self-signed CA
* **Throw away** the key for the root CA

The intermediary CA can be used to sign any local certificate; it will refuse to sign any certificate
outside the development domain.
