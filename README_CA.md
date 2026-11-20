# Search & Savor — Vault PKI, Certificate Authority & cert-manager

## 1. Purpose

This document explains how TLS certificate management is configured for the Search & Savor Kubernetes application running on a Kind cluster.

The objective is to implement a certificate management architecture that resembles a production environment:

- Maintain an offline Root Certificate Authority (Root CA).
- Use an Intermediate Certificate Authority for issuing certificates.
- Store and operate the Intermediate CA through HashiCorp Vault PKI.
- Use cert-manager to automate certificate issuance and renewal.
- Authenticate cert-manager to Vault using Kubernetes ServiceAccount authentication.
- Store the resulting TLS certificate in Kubernetes for Envoy Gateway.
- Terminate HTTPS at the Gateway and route traffic to the application.

The design avoids storing the Intermediate CA private key in Kubernetes.

---

# 2. Architecture Overview

## 2.1 Certificate issuance architecture

```text
                   OFFLINE / LOCAL MACHINE
                 (Mac — ~/search-savor-pki)
                            
                   Root CA Private Key
                    (Encrypted)
                           |
                           | Signs
                           v
                 Intermediate CA Certificate
                           |
                           | Certificate + private key
                           | imported into Vault
                           v
+--------------------------------------------------+
|                  KIND CLUSTER                    |
|                                                  |
|  +--------------------------------------------+  |
|  |              Vault Namespace               |  |
|  |                                            |  |
|  |  HashiCorp Vault                           |  |
|  |                                            |  |
|  |  PKI Engine: pki_int/                      |  |
|  |                                            |  |
|  |  Intermediate CA private key               |  |
|  |  Intermediate CA certificate               |  |
|  |  Root CA certificate                       |  |
|  |                                            |  |
|  |  PKI Role: search-savor-gateway            |  |
|  |  Policy: cert-manager-pki-sign             |  |
|  +---------------------+----------------------+  |
|                        ^                         |
|                        | Kubernetes Auth          |
|                        |                          |
|  +---------------------+----------------------+  |
|  |             cert-manager Namespace         |  |
|  |                                            |  |
|  |  cert-manager controller                   |  |
|  |       |                                    |  |
|  |       | Requests short-lived SA token       |  |
|  |       v                                    |  |
|  |  cert-manager-vault-auth                   |  |
|  +---------------------+----------------------+  |
|                        |                         |
|                        | Vault PKI signing       |
|                        v                         |
|  +--------------------------------------------+  |
|  |              search-savor Namespace       |  |
|  |                                            |  |
|  |  cert-manager Issuer                       |  |
|  |       |                                    |  |
|  |       v                                    |  |
|  |  Certificate: search-savor-tls             |  |
|  |       |                                    |  |
|  |       v                                    |  |
|  |  Kubernetes TLS Secret                     |  |
|  |       |                                    |  |
|  |       v                                    |  |
|  |  Envoy Gateway                             |  |
|  |       |                                    |  |
|  |       v                                    |  |
|  |  HTTPS: search-savor.test                  |  |
|  +--------------------------------------------+  |
+--------------------------------------------------+
```

## 2.2 What each component does

| Component | Responsibility |
|---|---|
| Root CA | Establishes trust by signing the Intermediate CA |
| Intermediate CA | Signs application/server certificates |
| Vault PKI | Securely manages the Intermediate CA and issues certificates |
| Vault Kubernetes Auth | Authenticates Kubernetes workloads to Vault |
| Vault Policy | Restricts what cert-manager can do in Vault |
| Vault PKI Role | Defines which domains and certificate properties may be issued |
| cert-manager | Automates certificate requests and renewals |
| Kubernetes Issuer | Connects cert-manager to Vault |
| Kubernetes TLS Secret | Stores the application certificate and private key |
| Envoy Gateway | Presents the certificate to clients and terminates HTTPS |

---

# 3. Environment and Versions

The following environment was used during implementation.

| Component | Configuration |
|---|---|
| Kubernetes distribution | Kind |
| Kubernetes context | `kind-kind` |
| Kubernetes version | v1.35.0 |
| Helm | v3.14.4 |
| Vault | HashiCorp Vault Helm chart |
| cert-manager | v1.21.3 |
| Envoy Gateway | v1.10.0 |
| Application namespace | `search-savor` |
| Vault namespace | `vault` |
| cert-manager namespace | `cert-manager` |

### Namespaces

```bash
kubectl get namespaces
```

Relevant namespaces:

```text
vault
cert-manager
external-secrets
search-savor
envoy-gateway-system
```

---

# 4. Understanding the Certificate Authority Hierarchy

We created a two-level Certificate Authority hierarchy.

```text
              Search & Savor Root CA
                       |
                       | Signs
                       v
          Search & Savor Intermediate CA
                       |
                       | Signs
                       v
             search-savor.test
                Server Certificate
```

## 4.1 Root CA

The Root CA is the trust anchor.

Its private key is encrypted and remains on the Mac, outside Kubernetes and Vault.

The Root CA signs the Intermediate CA certificate.

Important properties:

- RSA 4096-bit key.
- Encrypted private key.
- Self-signed certificate.
- Validity: 10 years.
- `CA:TRUE`.
- `pathlen:1`.
- Key usage: `keyCertSign`, `cRLSign`.

## 4.2 Intermediate CA

The Intermediate CA performs the actual certificate signing.

Its private key and certificate were imported into Vault PKI.

Important properties:

- RSA 4096-bit key.
- Validity: 5 years.
- Signed by the Root CA.
- `CA:TRUE`.
- `pathlen:0`.
- Key usage: `digitalSignature`, `keyCertSign`, `cRLSign`.

Why use an Intermediate CA?

The Root CA is highly sensitive. Keeping it offline reduces the consequences of a compromise of the certificate issuance system.

If Vault is compromised, the attacker may be able to issue certificates using the Intermediate CA. However, the offline Root CA remains protected.

---

# 5. Creating the Root CA on macOS

Working directory:

```bash
mkdir -p ~/search-savor-pki
cd ~/search-savor-pki
```

## 5.1 Generate the encrypted Root CA private key

```bash
openssl genpkey \
  -algorithm RSA \
  -aes-256-cbc \
  -pkeyopt rsa_keygen_bits:4096 \
  -out search-savor-root-ca.key
```

OpenSSL prompts for a passphrase.

Important:

- Do not commit this key to Git.
- Do not upload it to Kubernetes.
- Do not upload it to Vault.
- Keep the passphrase secure.

## 5.2 Generate the Root CA certificate

```bash
openssl req -x509 \
  -new \
  -key search-savor-root-ca.key \
  -sha256 \
  -days 3650 \
  -out search-savor-root-ca.crt \
  -subj "/O=Search and Savor/OU=Certificate Authority/CN=Search and Savor Root CA" \
  -addext "basicConstraints=critical,CA:TRUE,pathlen:1" \
  -addext "keyUsage=critical,keyCertSign,cRLSign" \
  -addext "subjectKeyIdentifier=hash"
```

This creates:

```text
search-savor-root-ca.key
search-savor-root-ca.crt
```

The `.key` is private. The `.crt` is public.

## 5.3 Verify the Root CA

```bash
openssl x509 \
  -in search-savor-root-ca.crt \
  -noout \
  -text
```

Check:

```text
Subject: Search and Savor Root CA
Issuer: Search and Savor Root CA
CA:TRUE, pathlen:1
```

The Subject and Issuer match because this is a self-signed certificate.

Check the private key:

```bash
openssl pkey \
  -in search-savor-root-ca.key \
  -check \
  -noout
```

Expected:

```text
Key is valid
```

---

# 6. Creating the Intermediate CA

## 6.1 Generate the Intermediate CA private key

```bash
openssl genpkey \
  -algorithm RSA \
  -pkeyopt rsa_keygen_bits:4096 \
  -out search-savor-intermediate-ca.key
```

The Intermediate CA private key is unencrypted in the working directory because it must be imported into Vault PKI.

Protect it carefully. It must not be committed to Git or placed in a Kubernetes Secret.

## 6.2 Generate the Intermediate CA CSR

```bash
openssl req -new \
  -key search-savor-intermediate-ca.key \
  -out search-savor-intermediate-ca.csr \
  -subj "/O=Search and Savor/OU=Certificate Authority/CN=Search and Savor Intermediate CA"
```

A CSR is a Certificate Signing Request. It contains the public key and requested certificate identity, but not the private key.

Verify:

```bash
openssl req \
  -in search-savor-intermediate-ca.csr \
  -noout \
  -text
```

## 6.3 Create Intermediate CA extensions

Create:

`intermediate-ca.ext`

```ini
[ v3_intermediate_ca ]
basicConstraints = critical, CA:TRUE, pathlen:0
keyUsage = critical, digitalSignature, keyCertSign, cRLSign
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid, issuer
```

The `pathlen:0` setting means this Intermediate CA cannot issue another subordinate CA certificate.

## 6.4 Sign the Intermediate CA with the Root CA

```bash
openssl x509 -req \
  -in search-savor-intermediate-ca.csr \
  -CA search-savor-root-ca.crt \
  -CAkey search-savor-root-ca.key \
  -CAcreateserial \
  -out search-savor-intermediate-ca.crt \
  -days 1825 \
  -sha256 \
  -extfile intermediate-ca.ext \
  -extensions v3_intermediate_ca
```

OpenSSL prompts for the Root CA private key passphrase.

## 6.5 Verify the Intermediate CA certificate

```bash
openssl verify \
  -CAfile search-savor-root-ca.crt \
  search-savor-intermediate-ca.crt
```

Expected:

```text
search-savor-intermediate-ca.crt: OK
```

Inspect:

```bash
openssl x509 \
  -in search-savor-intermediate-ca.crt \
  -noout \
  -text
```

Check:

- Subject: Search and Savor Intermediate CA.
- Issuer: Search and Savor Root CA.
- `CA:TRUE, pathlen:0`.
- Key usage includes certificate signing.
- Validity is approximately five years.

---

# 7. Installing Vault in Kubernetes

Vault was installed using the official HashiCorp Helm chart.

## 7.1 Add the Helm repository

```bash
helm repo add hashicorp https://helm.releases.hashicorp.com
helm repo update
```

## 7.2 Create the Vault namespace

```bash
kubectl create namespace vault
```

## 7.3 Vault configuration

File:

`k8s/vault-values.yaml`

```yaml
global:
  enabled: true

injector:
  enabled: false

server:
  enabled: true

  dataStorage:
    enabled: true
    size: 1Gi

  standalone:
    enabled: true

  service:
    enabled: true
```

This is a standalone Vault deployment with persistent storage.

It is suitable for a local learning environment, not a production HA deployment.

## 7.4 Install Vault

```bash
helm install vault \
  hashicorp/vault \
  --namespace vault \
  --values k8s/vault-values.yaml
```

Check:

```bash
kubectl get pods -n vault
kubectl get services -n vault
```

## 7.5 Access Vault locally

```bash
kubectl port-forward \
  -n vault \
  service/vault \
  8200:8200
```

Vault is now accessible at:

```text
http://localhost:8200
```

Keep this port-forward terminal open.

---

# 8. Vault Initialization and Unsealing

Vault was initialized using Shamir's Secret Sharing.

The initialization process produced:

- Five unseal keys.
- An unseal threshold of three.
- An initial root token.

The user saved these credentials privately.

**Never store unseal keys or the Vault root token in Git, Kubernetes manifests, README files, or chat messages.**

## 8.1 Unseal Vault

After a restart, Vault may need to be unsealed.

Use:

```bash
kubectl exec -it \
  vault-0 \
  -n vault \
  -- vault operator unseal
```

Enter an unseal key when prompted.

Repeat using three distinct unseal keys.

Check:

```bash
kubectl exec -it \
  vault-0 \
  -n vault \
  -- vault status
```

Vault should report:

```text
Sealed: false
```

## 8.2 Authenticate to Vault from macOS

Set the token without printing it:

```bash
read -s "VAULT_TOKEN?Enter your Vault token: "
export VAULT_TOKEN
echo
```

The token is now available in the current shell.

Avoid commands that print `$VAULT_TOKEN`.

---

# 9. Vault PKI Secrets Engine

Vault PKI is responsible for issuing and managing certificates.

The existing PKI mount was:

```text
pki_int/
```

We reused this existing mount instead of enabling a second one.

## 9.1 Check enabled secrets engines

```bash
vault secrets list -detailed
```

Find:

```text
pki_int/    pki
```

Check the mount configuration:

```bash
vault read sys/mounts/pki_int/tune
```

The existing default and maximum lease TTL values were 768 hours.

## 9.2 Inspect existing issuers

```bash
vault read pki_int/config/issuers
```

Initially, no default issuer was configured.

The Root CA and Intermediate CA were subsequently imported.

---

# 10. Importing the Intermediate CA into Vault PKI

The Intermediate CA private key must be available to Vault because Vault will use it to sign server certificates.

The Root CA private key stays offline.

## 10.1 Create the CA bundle

In `~/search-savor-pki`, create:

`intermediate-ca-bundle.pem`

Its contents are in this order:

```text
-----BEGIN CERTIFICATE-----
Intermediate CA certificate
-----END CERTIFICATE-----

-----BEGIN PRIVATE KEY-----
Intermediate CA private key
-----END PRIVATE KEY-----

-----BEGIN CERTIFICATE-----
Root CA certificate
-----END CERTIFICATE-----
```

Use the actual PEM contents from these files:

```text
search-savor-intermediate-ca.crt
search-savor-intermediate-ca.key
search-savor-root-ca.crt
```

Do not put the Root CA private key in this bundle.

Protect the bundle:

```bash
chmod 600 intermediate-ca-bundle.pem
```

## 10.2 Create the JSON payload

```bash
jq -n \
  --rawfile pem_bundle intermediate-ca-bundle.pem \
  '{pem_bundle: $pem_bundle}' \
  > vault-ca-import.json
```

Protect it too:

```bash
chmod 600 vault-ca-import.json
```

The JSON file contains the Intermediate CA private key encoded as a string. Treat it as a sensitive private-key file.

## 10.3 Import into Vault

With the Vault port-forward running:

```bash
curl --fail-with-body --silent --show-error \
  --request POST \
  --header "X-Vault-Token: $VAULT_TOKEN" \
  --header "Content-Type: application/json" \
  --data-binary @vault-ca-import.json \
  http://localhost:8200/v1/pki_int/config/ca
```

The initial response did not clearly show imported issuer IDs. We therefore verified the actual issuer records.

## 10.4 List imported issuers

The Vault endpoint requires an HTTP LIST operation.

Using Vault CLI:

```bash
vault list pki_int/issuers
```

Two issuer IDs were found:

```text
98b62d32-f9c4-bbb3-957e-62b20abe80f4
f015fd5d-55ae-e411-55fb-65a5c809f722
```

The first is the Intermediate CA. The second is the Root CA.

Inspect an issuer:

```bash
vault read pki_int/issuer/98b62d32-f9c4-bbb3-957e-62b20abe80f4
```

The Intermediate issuer should show:

```text
Subject: Search and Savor Intermediate CA
Issuer: Search and Savor Root CA
```

## 10.5 Configure the Intermediate CA as the default issuer

We selected the Intermediate CA as the default signing issuer.

```bash
curl --fail-with-body --silent --show-error \
  --request POST \
  --header "X-Vault-Token: $VAULT_TOKEN" \
  --header "Content-Type: application/json" \
  --data '{
    "default": "98b62d32-f9c4-bbb3-957e-62b20abe80f4",
    "default_follows_latest_issuer": false
  }' \
  http://localhost:8200/v1/pki_int/config/issuers
```

Verify:

```bash
vault read pki_int/config/issuers
```

Expected default:

```text
98b62d32-f9c4-bbb3-957e-62b20abe80f4
```

This ensures that certificates are signed by the Intermediate CA, not directly by the Root CA.

---

# 11. Creating a Vault PKI Role

A Vault PKI role restricts which certificates can be issued.

We created:

```text
search-savor-gateway
```

The role allows the Gateway hostname:

```text
search-savor.test
```

## 11.1 Create the PKI role

```bash
curl --fail-with-body --silent --show-error \
  --request POST \
  --header "X-Vault-Token: $VAULT_TOKEN" \
  --header "Content-Type: application/json" \
  --data '{
    "allowed_domains": ["search-savor.test"],
    "allow_bare_domains": true,
    "allow_subdomains": false,
    "allow_glob_domains": false,
    "allow_wildcard_certificates": false,
    "allow_ip_sans": false,
    "allow_any_name": false,
    "server_flag": true,
    "client_flag": false,
    "key_type": "rsa",
    "key_bits": 2048,
    "ttl": "720h",
    "max_ttl": "720h",
    "enforce_hostnames": true
  }' \
  http://localhost:8200/v1/pki_int/roles/search-savor-gateway
```

## 11.2 What the role settings mean

| Setting | Purpose |
|---|---|
| allowed_domains | Permitted DNS names |
| allow_bare_domains | Allows `search-savor.test` itself |
| allow_subdomains | Disallows arbitrary subdomains |
| allow_wildcard_certificates | Disallows wildcard certificates |
| allow_ip_sans | Disallows IP address SANs |
| allow_any_name | Prevents unrestricted names |
| server_flag | Enables server certificate usage |
| client_flag | Disables client certificate usage |
| key_type | RSA |
| key_bits | 2048 |
| ttl | 30 days |
| max_ttl | Maximum 30 days |
| enforce_hostnames | Enforces valid hostnames |

## 11.3 Verify the role

```bash
vault read pki_int/roles/search-savor-gateway
```

Confirm the domain restrictions and TTL.

The 30-day TTL means cert-manager needs to renew the certificate before it expires.

---

# 12. Vault Policy for cert-manager

Vault policies define which API paths a Vault identity can access.

We created a policy named:

```text
cert-manager-pki-sign
```

Its only permission is to sign certificates using the designated PKI role.

## 12.1 Policy definition

```hcl
path "pki_int/sign/search-savor-gateway" {
  capabilities = ["update"]
}
```

## 12.2 Create the policy

```bash
curl --fail-with-body --silent --show-error \
  --request POST \
  --header "X-Vault-Token: $VAULT_TOKEN" \
  --header "Content-Type: application/json" \
  --data '{
    "policy": "path \"pki_int/sign/search-savor-gateway\" { capabilities = [\"update\"] }"
  }' \
  http://localhost:8200/v1/sys/policies/acl/cert-manager-pki-sign
```

## 12.3 Verify the policy

```bash
vault policy read cert-manager-pki-sign
```

Expected:

```hcl
path "pki_int/sign/search-savor-gateway" {
  capabilities = ["update"]
}
```

This follows the principle of least privilege: cert-manager can sign certificates through this specific role, rather than administer Vault or access the Root CA.

---

# 13. Enabling Vault Kubernetes Authentication

Vault must authenticate cert-manager without requiring a static Vault token in Kubernetes.

We use Kubernetes ServiceAccount JWT authentication.

## 13.1 Enable the Kubernetes auth method

This was already enabled:

```bash
vault auth enable kubernetes
```

If it is already enabled, do not run this command again.

Check:

```bash
vault auth list
```

Look for:

```text
kubernetes/
```

## 13.2 Create the Vault authentication ServiceAccount

Vault itself uses a dedicated ServiceAccount in the `vault` namespace.

A ClusterRoleBinding grants it the `system:auth-delegator` role.

This allows Vault to validate Kubernetes tokens through TokenReview.

The binding was named:

```text
vault-auth-delegator
```

Check:

```bash
kubectl get clusterrolebinding vault-auth-delegator -o yaml
```

The Vault ServiceAccount should have permission to create TokenReview requests.

## 13.3 Configure Kubernetes authentication in Vault

Vault is running inside Kubernetes and uses its locally mounted ServiceAccount token and CA.

The configuration was performed from inside the Vault Pod:

```bash
kubectl exec -it vault-0 -n vault -- sh
```

Then:

```bash
export KUBERNETES_HOST="https://${KUBERNETES_SERVICE_HOST}:${KUBERNETES_SERVICE_PORT}"
```

Configure:

```bash
vault write auth/kubernetes/config \
  kubernetes_host="$KUBERNETES_HOST" \
  token_reviewer_jwt="" \
  kubernetes_ca_cert=""
```

The empty token and CA values use Vault's local ServiceAccount token and mounted CA.

Verify:

```bash
vault read auth/kubernetes/config
```

The configuration showed:

```text
disable_local_ca_jwt false
token_reviewer_jwt_set false
```

This is expected for the locally mounted token/CA configuration.

---

# 14. Installing cert-manager

cert-manager automates certificate lifecycle management in Kubernetes.

It creates CertificateRequests, contacts the configured issuer, stores the issued certificate, and renews it before expiry.

## 14.1 Install cert-manager

The official Jetstack Helm chart was used.

```bash
helm install cert-manager \
  oci://quay.io/jetstack/charts/cert-manager \
  --version v1.21.3 \
  --namespace cert-manager \
  --create-namespace \
  --set crds.enabled=true
```

## 14.2 Verify installation

```bash
kubectl get pods -n cert-manager
```

Expected components:

```text
cert-manager
cert-manager-cainjector
cert-manager-webhook
```

All should be Running and Ready.

Check CRDs:

```bash
kubectl get crds | grep cert-manager
```

---

# 15. cert-manager Authentication to Vault

This is a critical security boundary.

cert-manager does not receive the Vault root token.

Instead:

1. cert-manager requests a short-lived Kubernetes token.
2. The token belongs to `cert-manager-vault-auth`.
3. The token has the audience `vault`.
4. cert-manager sends it to Vault's Kubernetes login endpoint.
5. Vault validates the token using Kubernetes TokenReview.
6. Vault checks the ServiceAccount and namespace against its auth role.
7. Vault returns a short-lived Vault token with the restricted policy.

## 15.1 Create the dedicated ServiceAccount

File:

`k8s/cert-manager/vault-service-account.yaml`

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: cert-manager-vault-auth
  namespace: cert-manager
automountServiceAccountToken: false
```

Apply:

```bash
kubectl apply -f cert-manager/vault-service-account.yaml
```

This ServiceAccount is specifically for Vault authentication.

It is separate from cert-manager's normal controller ServiceAccount.

## 15.2 Allow cert-manager to request a token

File:

`k8s/cert-manager/vault-token-rbac.yaml`

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: cert-manager-vault-token-requester
  namespace: cert-manager
rules:
  - apiGroups: [""]
    resources:
      - serviceaccounts/token
    verbs:
      - create
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: cert-manager-vault-token-requester
  namespace: cert-manager
subjects:
  - kind: ServiceAccount
    name: cert-manager
    namespace: cert-manager
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: cert-manager-vault-token-requester
```

Apply:

```bash
kubectl apply -f cert-manager/vault-token-rbac.yaml
```

**Important RBAC consideration:** Kubernetes RBAC cannot reliably restrict `create` on the `serviceaccounts/token` subresource to a single ServiceAccount using `resourceNames`. This Role is namespace-scoped, but permits the cert-manager controller to request tokens for ServiceAccounts in the `cert-manager` namespace.

For a production environment, review whether a more isolated authentication architecture is appropriate.

## 15.3 Verify the permission

```bash
kubectl auth can-i create serviceaccounts/token \
  --as=system:serviceaccount:cert-manager:cert-manager \
  --as-group=system:serviceaccounts \
  --as-group=system:serviceaccounts:cert-manager \
  --as-group=system:authenticated \
  -n cert-manager
```

An explicit subresource check also returned:

```bash
kubectl auth can-i create serviceaccounts \
  --subresource=token \
  --as=system:serviceaccount:cert-manager:cert-manager \
  --as-group=system:serviceaccounts \
  --as-group=system:serviceaccounts:cert-manager \
  --as-group=system:authenticated \
  -n cert-manager
```

Expected:

```text
yes
```

The explicit subresource form is the verified check used in this setup.

## 15.4 Why the audience matters

The token audience is:

```text
vault
```

An audience identifies the intended recipient of a token.

A token intended for Vault should not automatically be accepted by unrelated services.

The ServiceAccount reference, Vault auth role, and issued token must all use the same audience.

---

# 16. Creating the Vault Kubernetes Auth Role for cert-manager

Vault needs to know which Kubernetes identity is allowed to authenticate.

We created the role:

```text
cert-manager-pki
```

## 16.1 Create the role

```bash
curl --fail-with-body --silent --show-error \
  --request POST \
  --header "X-Vault-Token: $VAULT_TOKEN" \
  --header "Content-Type: application/json" \
  --data '{
    "bound_service_account_names": ["cert-manager-vault-auth"],
    "bound_service_account_namespaces": ["cert-manager"],
    "audience": "vault",
    "policies": ["cert-manager-pki-sign"],
    "ttl": "1h"
  }' \
  http://localhost:8200/v1/auth/kubernetes/role/cert-manager-pki
```

## 16.2 Verify

```bash
curl --fail-with-body --silent --show-error \
  --header "X-Vault-Token: $VAULT_TOKEN" \
  http://localhost:8200/v1/auth/kubernetes/role/cert-manager-pki | jq
```

Verified settings:

| Property | Value |
|---|---|
| Role | `cert-manager-pki` |
| ServiceAccount | `cert-manager-vault-auth` |
| Namespace | `cert-manager` |
| Audience | `vault` |
| Policy | `cert-manager-pki-sign` |
| Token TTL | 3600 seconds |

This prevents arbitrary Kubernetes workloads from using the role.

---

# 17. cert-manager Vault Issuer

**Implementation status: Configuration prepared; application and validation are the next step.**

The Issuer connects cert-manager to Vault.

File:

`k8s/cert-manager/vault-issuer.yaml`

```yaml
apiVersion: cert-manager.io/v1
kind: Issuer
metadata:
  name: search-savor-vault-issuer
  namespace: search-savor
spec:
  vault:
    server: http://vault.vault.svc.cluster.local:8200
    path: pki_int/sign/search-savor-gateway
    auth:
      kubernetes:
        mountPath: /v1/auth/kubernetes/login
        role: cert-manager-pki
        serviceAccountRef:
          name: cert-manager-vault-auth
          audiences:
            - vault
```

### Explanation

| Field | Meaning |
|---|---|
| server | Internal Vault Kubernetes DNS |
| path | Vault PKI signing endpoint |
| mountPath | Vault Kubernetes authentication endpoint |
| role | Vault Kubernetes auth role |
| serviceAccountRef | ServiceAccount cert-manager uses to authenticate |
| audiences | Expected token audience |

The Vault server address:

```text
http://vault.vault.svc.cluster.local:8200
```

Breakdown:

- `vault`: Kubernetes Service name.
- First `vault`: namespace.
- `svc.cluster.local`: Kubernetes service DNS suffix.
- `8200`: Vault service port.

Apply after checking the configuration:

```bash
kubectl apply -f cert-manager/vault-issuer.yaml
```

Check:

```bash
kubectl get issuer -n search-savor
```

Inspect:

```bash
kubectl describe issuer search-savor-vault-issuer -n search-savor
```

The target is:

```text
Ready: True
```

If it is not Ready, inspect the cert-manager logs:

```bash
kubectl logs deployment/cert-manager \
  -n cert-manager \
  --tail=100
```

Also inspect Issuer events:

```bash
kubectl describe issuer search-savor-vault-issuer \
  -n search-savor
```

---

# 18. Requesting the HTTPS Certificate

**Not yet completed.**

Once the Issuer is Ready, create a Certificate resource.

Proposed file:

`k8s/gateway/search-savor-certificate.yaml`

```yaml
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: search-savor-certificate
  namespace: search-savor
spec:
  secretName: search-savor-tls
  issuerRef:
    name: search-savor-vault-issuer
    kind: Issuer
    group: cert-manager.io
  dnsNames:
    - search-savor.test
  duration: 720h
  renewBefore: 168h
  privateKey:
    algorithm: RSA
    size: 2048
    rotationPolicy: Always
  usages:
    - digital signature
    - key encipherment
    - server auth
```

The important values:

- Certificate hostname: `search-savor.test`.
- TLS Secret: `search-savor-tls`.
- Certificate lifetime: 30 days.
- Renewal window: 7 days before expiration.
- Private key rotation: enabled.

Apply:

```bash
kubectl apply -f gateway/search-savor-certificate.yaml
```

Check:

```bash
kubectl get certificate -n search-savor
kubectl describe certificate search-savor-certificate -n search-savor
```

Check the generated Secret:

```bash
kubectl get secret search-savor-tls -n search-savor
```

Do not print the Secret's private key.

A TLS Secret should contain:

```text
tls.crt
tls.key
```

The certificate chain should be inspected to confirm the Intermediate CA is included as needed by the client trust chain.

---

# 19. Connecting the Certificate to Envoy Gateway

The Gateway is configured to terminate HTTPS.

Planned file:

`k8s/gateway/gateway.yaml`

```yaml
apiVersion: gateway.networking.k8s.io/v1
kind: Gateway
metadata:
  name: search-savor-gateway
  namespace: search-savor
  labels:
    app.kubernetes.io/name: search-savor
    app.kubernetes.io/component: gateway
spec:
  gatewayClassName: search-savor-gateway-class
  listeners:
    - name: https
      hostname: search-savor.test
      port: 443
      protocol: HTTPS
      tls:
        mode: Terminate
        certificateRefs:
          - kind: Secret
            name: search-savor-tls
      allowedRoutes:
        namespaces:
          from: Same
        kinds:
          - kind: HTTPRoute
```

The certificate Secret and Gateway must be in the same namespace for this configuration.

The traffic path will be:

```text
Browser
   |
   | HTTPS :443
   v
Envoy Gateway
   |
   | TLS termination
   |
   | HTTP inside the cluster
   v
Frontend Service
   |
   v
Frontend Pod (Nginx)
   |
   | /api/ proxy
   v
Backend Service
   |
   v
Backend Pod (FastAPI)
```

The Gateway handles external HTTPS. The frontend Nginx continues to proxy API requests to the backend Service.

---

# 20. Local Certificate Trust

The certificate chain is:

```text
Search & Savor Root CA
          |
          v
Search & Savor Intermediate CA
          |
          v
search-savor.test
```

A browser must trust the Root CA certificate.

For local testing, the public Root CA certificate can be installed in the macOS System Keychain and marked as trusted.

The file to install is:

```text
search-savor-root-ca.crt
```

**Never install or distribute `search-savor-root-ca.key`.**

The Root CA private key is not needed by browsers.

The `.test` domain is reserved for testing. It does not automatically resolve through public DNS.

For local browser testing, configure the local hostname resolution so that:

```text
search-savor.test
```

resolves to the address where the Gateway is exposed.

The current Kind cluster does not have host port 443 mapped. We will need to configure local Gateway exposure, for example using port-forwarding or a suitable NodePort arrangement.

---

# 21. Important Security Principles

## 21.1 Keep the Root CA offline

The Root CA private key should remain outside Kubernetes and Vault.

It should be encrypted and backed up securely.

## 21.2 Do not put the Intermediate CA key in Kubernetes

The Intermediate CA key belongs in Vault PKI.

Kubernetes should receive only the application-specific TLS certificate and private key needed by the Gateway.

## 21.3 Do not use the Vault root token for applications

The Vault root token is an administrative credential.

cert-manager authenticates using Kubernetes ServiceAccount authentication and receives a restricted Vault token.

## 21.4 Use least privilege

The cert-manager Vault policy allows only:

```text
pki_int/sign/search-savor-gateway
```

It cannot administer Vault or manage the PKI engine.

## 21.5 Protect generated files

The following files contain sensitive private key material:

```text
search-savor-root-ca.key
search-savor-intermediate-ca.key
intermediate-ca-bundle.pem
vault-ca-import.json
```

Do not commit these files to Git.

Recommended permissions:

```bash
chmod 600 search-savor-root-ca.key
chmod 600 search-savor-intermediate-ca.key
chmod 600 intermediate-ca-bundle.pem
chmod 600 vault-ca-import.json
```

Use secure backups before removing any files.

## 21.6 Rotate exposed credentials

A Vault root token was exposed during an earlier troubleshooting exchange.

Treat it as compromised and rotate it before production use. Do not reuse an exposed administrative token as a long-term credential.

---

# 22. Troubleshooting Commands

## Vault

Check status:

```bash
vault status
```

Check PKI engine:

```bash
vault secrets list -detailed
```

List issuers:

```bash
vault list pki_int/issuers
```

Inspect default issuer:

```bash
vault read pki_int/config/issuers
```

Inspect PKI role:

```bash
vault read pki_int/roles/search-savor-gateway
```

Inspect policy:

```bash
vault policy read cert-manager-pki-sign
```

Inspect Kubernetes auth role:

```bash
vault read auth/kubernetes/role/cert-manager-pki
```

## cert-manager

Check components:

```bash
kubectl get pods -n cert-manager
```

Check Issuer:

```bash
kubectl get issuer -n search-savor
```

Describe Issuer:

```bash
kubectl describe issuer search-savor-vault-issuer -n search-savor
```

Check Certificates:

```bash
kubectl get certificates -n search-savor
```

Check CertificateRequests:

```bash
kubectl get certificaterequests -n search-savor
```

Check events:

```bash
kubectl get events -n search-savor --sort-by=.lastTimestamp
```

Check logs:

```bash
kubectl logs deployment/cert-manager -n cert-manager --tail=100
```

## TLS Secret

Check whether it exists:

```bash
kubectl get secret search-savor-tls -n search-savor
```

Inspect certificate metadata without printing the private key:

```bash
kubectl get secret search-savor-tls \
  -n search-savor \
  -o jsonpath='{.data.tls\.crt}' \
  | base64 -d \
  | openssl x509 -noout -subject -issuer -dates -ext subjectAltName
```

---

# 23. Current Implementation Status

| Task | Status |
|---|---|
| Kind cluster | Complete |
| Vault installed | Complete |
| Vault initialized and unsealed | Complete |
| Root CA created | Complete |
| Intermediate CA created | Complete |
| Intermediate CA signed by Root CA | Complete |
| Intermediate CA imported into Vault PKI | Complete |
| Default PKI issuer configured | Complete |
| Vault PKI role created | Complete |
| Vault signing policy created | Complete |
| Vault Kubernetes authentication enabled | Complete |
| Vault Kubernetes auth configured | Complete |
| cert-manager installed | Complete |
| cert-manager Vault ServiceAccount created | Complete |
| cert-manager TokenRequest RBAC configured | Complete |
| TokenRequest permission verified | Complete |
| Vault Kubernetes auth role created | Complete |
| Vault Issuer manifest prepared | Next step |
| Vault Issuer Ready=True | Pending |
| Certificate resource created | Pending |
| TLS Secret generated | Pending |
| Gateway configured for HTTPS | Pending |
| Local Root CA trust configured | Pending |
| HTTPS browser test | Pending |

---

# 24. Next Steps

Resume in this order:

1. Apply `cert-manager/vault-issuer.yaml`.
2. Verify that `search-savor-vault-issuer` becomes Ready.
3. Troubleshoot any Vault authentication or signing errors.
4. Create the Certificate resource.
5. Verify that `search-savor-tls` is generated.
6. Inspect the certificate's Subject, Issuer, SAN, and validity.
7. Configure the Envoy Gateway HTTPS listener.
8. Configure local Gateway exposure and hostname resolution.
9. Install the Root CA public certificate into the macOS trust store.
10. Test `https://search-savor.test`.
11. Confirm that cert-manager renews the certificate before expiration.

---

# 25. Important Production Considerations

This is a production-oriented learning architecture, but the current local implementation is not yet production-ready.

Before production:

- Use a highly available Vault deployment with appropriate storage and recovery procedures.
- Configure Vault TLS rather than relying on HTTP between cert-manager and Vault.
- Use a hardened, backed-up Root CA and Intermediate CA lifecycle.
- Rotate the exposed Vault root token.
- Protect and back up Vault's storage and recovery material.
- Review Kubernetes RBAC, especially TokenRequest permissions.
- Consider network policies restricting access to Vault.
- Monitor certificate expiry and renewal failures.
- Configure certificate revocation and CRL/OCSP distribution if required.
- Use a real domain and an appropriate public or enterprise trust model for externally accessible services.
- Test disaster recovery, CA rotation, and certificate renewal before relying on this architecture.

**Remember:** Vault PKI manages certificate issuance, cert-manager automates the Kubernetes certificate lifecycle, and Envoy Gateway presents the certificate to clients. Each component has a distinct responsibility.

