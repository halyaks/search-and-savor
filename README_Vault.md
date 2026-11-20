# Search & Savor — Kubernetes Secret Management with HashiCorp Vault and External Secrets Operator

## 1. Overview

This document explains how secret management was configured for the Search & Savor application running on Kubernetes using Kind.

The application has a React + Vite frontend and a FastAPI backend. The backend uses the YouTube Data API and requires an API key to communicate with Google's API.

Initially, the API key was available through the local Docker Compose environment configuration. However, Kubernetes does not automatically inherit environment variables or `.env` files from Docker Compose.

We therefore implemented a centralized secret-management solution using:

- **HashiCorp Vault** — stores sensitive application credentials.
- **Kubernetes ServiceAccounts** — provide identities to Kubernetes workloads.
- **Kubernetes RBAC** — controls which identities can perform specific operations.
- **External Secrets Operator (ESO)** — retrieves secrets from Vault and synchronizes them into Kubernetes Secrets.
- **Kubernetes Secrets** — provide the API key to the backend container as an environment variable.

The backend receives the API key without having the actual value hardcoded in its Deployment manifest or application source code.

---

## 2. Architecture

### 2.1 Secret-management architecture

The implemented workflow is:

```text
                 HASHICORP VAULT
                Namespace: vault
                       |
                       |
            Stores API_KEY securely
                       |
                       |
             Kubernetes Auth Method
                       |
                       |
                       v
           EXTERNAL SECRETS OPERATOR
           Namespace: external-secrets
                       |
             Authenticates using
             Kubernetes ServiceAccount
                       |
                       |
              Reads secret from Vault
                       |
                       v
                EXTERNAL SECRET
                Namespace: search-savor
                       |
                       |
              Synchronizes the value
                       |
                       v
               KUBERNETES SECRET
               search-savor-secrets
                       |
                       |
               Environment injection
                       |
                       v
                FASTAPI BACKEND
                Namespace: search-savor
                       |
                       |
                YOUTUBE_API_KEY
                       |
                       v
                 YOUTUBE DATA API
```

### 2.2 Namespaces

We separated the components into three Kubernetes namespaces.

| Namespace | Purpose |
|---|---|
| `vault` | Runs HashiCorp Vault |
| `external-secrets` | Runs External Secrets Operator |
| `search-savor` | Runs the application and its synchronized secrets |

Why use separate namespaces?

Namespaces provide logical separation between workloads and allow us to scope Kubernetes RBAC permissions.

For example, the application backend does not need to run in the same namespace as Vault or ESO.

---

## 3. Why We Needed Vault

Before implementing Vault, the API key was supplied through environment configuration.

This is acceptable for local development, but managing credentials becomes more complicated when applications run in Kubernetes.

Some common problems with hardcoding secrets include:

- Accidentally committing credentials to Git.
- Duplicating credentials across multiple YAML files.
- Having no centralized place to rotate credentials.
- Giving unnecessary access to sensitive values.
- Making it difficult to manage credentials across environments.

Vault provides a centralized secret store.

Instead of placing the API key directly in a Deployment manifest, we store it in Vault and let ESO retrieve it.

Our Vault secret path is:

```text
secret/search-savor/youtube
```

The key stored inside that secret is:

```text
API_KEY
```

The application-facing environment variable is:

```text
YOUTUBE_API_KEY
```

These names can differ because ESO maps a Vault property to a Kubernetes Secret key.

---

# PART 1 — HASHICORP VAULT INSTALLATION

## 4. Install HashiCorp Vault

We used the official HashiCorp Helm chart.

### 4.1 Add the Helm repository

```bash
helm repo add hashicorp https://helm.releases.hashicorp.com
```

Update the repository:

```bash
helm repo update
```

### 4.2 Create the Vault namespace

```bash
kubectl create namespace vault
```

### 4.3 Configure Vault

We created:

```text
k8s/vault-values.yaml
```

Configuration:

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

### Explanation

**global.enabled**

Enables Vault chart resources.

**injector.enabled: false**

Disables the Vault Agent Injector.

We are not injecting secrets directly through Vault Agent sidecars. ESO is responsible for retrieving and synchronizing secrets.

**server.enabled**

Enables the Vault server.

**dataStorage.enabled**

Enables persistent storage for Vault.

**size: 1Gi**

Allocates a 1 GiB persistent volume claim.

**standalone.enabled**

Runs Vault in standalone mode.

This is appropriate for our local Kind learning environment, but it is not a highly available production configuration.

### 4.4 Install Vault

```bash
helm install vault hashicorp/vault \
  --namespace vault \
  --values k8s/vault-values.yaml
```

Verify the installation:

```bash
kubectl get pods -n vault
```

Check the services:

```bash
kubectl get services -n vault
```

Check persistent storage:

```bash
kubectl get pvc -n vault
```

The Vault service is accessible inside the cluster at:

```text
http://vault.vault.svc.cluster.local:8200
```

This DNS name follows the Kubernetes Service DNS convention:

```text
<service-name>.<namespace>.svc.cluster.local
```

---

## 5. Initialize and Unseal Vault

Installing Vault does not automatically make it ready to store secrets.

Vault must first be initialized and unsealed.

### 5.1 Initialize Vault

We accessed the Vault Pod:

```bash
kubectl exec -it vault-0 -n vault -- sh
```

Then initialized Vault:

```bash
vault operator init
```

Vault generated:

- Five unseal keys.
- One initial root token.

The default Shamir configuration used:

```text
Total unseal keys: 5
Required unseal keys: 3
```

### Important security warning

The unseal keys and root token are highly sensitive.

They must:

- Never be committed to Git.
- Never be shared in chat.
- Never be included in application configuration.
- Be stored securely outside the cluster.

The root token should be used only for initial administration and necessary administrative operations.

### 5.2 Unseal Vault

After initialization, Vault starts in a sealed state.

We needed three different unseal keys to unseal it.

From inside the Vault Pod:

```bash
vault operator unseal
```

Enter the first key when prompted.

Repeat the command with two additional, different keys.

Check the status:

```bash
vault status
```

Expected:

```text
Sealed          false
```

### Why does Vault need unsealing?

Vault encrypts its stored data.

Unsealing allows Vault to access the encryption key material needed to operate.

In this standalone learning setup, Vault needs to be unsealed manually after a restart.

This is one of the operational limitations of our current setup.

---

# PART 2 — KUBERNETES SERVICEACCOUNTS AND RBAC

## 6. Understanding Kubernetes ServiceAccounts

A ServiceAccount represents an identity for a process running inside Kubernetes.

Pods can use ServiceAccounts to authenticate when communicating with the Kubernetes API.

We created separate identities for different components rather than using the default ServiceAccount for everything.

Our setup uses these identities:

| ServiceAccount | Namespace | Purpose |
|---|---|---|
| `vault` | `vault` | Allows Vault to authenticate to Kubernetes |
| `external-secrets` | `external-secrets` | ESO controller identity |
| `eso-vault-auth` | `search-savor` | Identity ESO uses when authenticating to Vault |
| `backend-sa` | `search-savor` | Identity used by the FastAPI backend |

The important distinction is:

- The ESO controller ServiceAccount runs the ESO controller.
- The `eso-vault-auth` ServiceAccount is the identity whose short-lived token ESO obtains and presents to Vault.
- The backend ServiceAccount is independent of both.

---

## 7. Configure Vault Kubernetes Authentication

Vault needs a way to verify that an application or controller is running under a particular Kubernetes ServiceAccount.

For this, we enabled Vault's Kubernetes authentication method.

### 7.1 Create RBAC permission for Vault

Vault uses Kubernetes TokenReview API to validate ServiceAccount tokens.

The Vault ServiceAccount therefore needs permission to perform token reviews.

We created:

```text
k8s/vault-auth-rbac.yaml
```

Manifest:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: vault-auth-delegator

roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: system:auth-delegator

subjects:
  - kind: ServiceAccount
    name: vault
    namespace: vault
```

Apply:

```bash
kubectl apply -f k8s/vault-auth-rbac.yaml
```

### Explanation

`system:auth-delegator` is a built-in Kubernetes ClusterRole.

It grants the permissions needed for delegated authentication operations, including token review.

The ClusterRoleBinding connects that permission to the Vault ServiceAccount.

We verified the permission:

```bash
kubectl auth can-i create tokenreviews.authentication.k8s.io \
  --as=system:serviceaccount:vault:vault
```

Expected:

```text
yes
```

### 7.2 Enable Kubernetes authentication in Vault

Access Vault:

```bash
kubectl exec -it vault-0 -n vault -- sh
```

Set the Vault address:

```bash
export VAULT_ADDR=http://127.0.0.1:8200
```

Authenticate using the initial Vault root token when prompted:

```bash
vault login
```

Enable Kubernetes authentication:

```bash
vault auth enable kubernetes
```

### 7.3 Configure Kubernetes authentication

Vault runs inside Kubernetes and has its own mounted ServiceAccount token and Kubernetes CA certificate.

We configured Kubernetes authentication to use Vault's local mounted credentials.

```bash
vault write auth/kubernetes/config \
  kubernetes_host="https://${KUBERNETES_SERVICE_HOST}:${KUBERNETES_SERVICE_PORT}" \
  kubernetes_ca_cert=@/var/run/secrets/kubernetes.io/serviceaccount/ca.crt \
  token_reviewer_jwt=@/var/run/secrets/kubernetes.io/serviceaccount/token
```

We subsequently configured the local-CA/local-JWT behavior:

```bash
vault write auth/kubernetes/config \
  kubernetes_host="https://${KUBERNETES_SERVICE_HOST}:${KUBERNETES_SERVICE_PORT}" \
  token_reviewer_jwt="" \
  kubernetes_ca_cert=""
```

Vault's configuration uses its locally mounted ServiceAccount credentials rather than retaining a separately supplied reviewer token.

Check the configuration:

```bash
vault read auth/kubernetes/config
```

The configuration should indicate that local CA/JWT use is enabled and that no explicit reviewer token is stored.

One detail:

```text
token_reviewer_jwt_set: false
```

is expected with this local-token approach. It does not mean Kubernetes authentication is disabled.

---

## 8. Configure Vault's KV Version 2 Secret Engine

Vault provides secret engines for storing and retrieving data.

We used the KV Version 2 secret engine.

KV v2 supports secret versioning, allowing previous versions of a secret to be retained.

Check the existing mount:

```bash
vault secrets list
```

We found that `secret/` was already enabled and configured as KV v2.

Verify:

```bash
vault read sys/mounts/secret/tune
```

The version should be:

```text
2
```

Do not enable another secret engine at the same mount path if it already exists.

### Understanding the KV v2 paths

We use:

```text
secret/search-savor/youtube
```

However, Vault internally uses different API paths for reading and metadata operations.

For KV v2:

```text
secret/data/search-savor/youtube
```

is the data endpoint.

And:

```text
secret/metadata/search-savor/youtube
```

is the metadata endpoint.

This distinction matters when writing Vault policies.

---

## 9. Create a Vault Policy for ESO

We do not want ESO to have unrestricted access to Vault.

Instead, we created a policy called:

```text
search-savor-read
```

Policy:

```hcl
path "secret/data/search-savor/*" {
  capabilities = ["read"]
}

path "secret/metadata/search-savor/*" {
  capabilities = ["list"]
}
```

Create it from inside the Vault Pod:

```bash
vault policy write search-savor-read - <<'EOF'
path "secret/data/search-savor/*" {
  capabilities = ["read"]
}

path "secret/metadata/search-savor/*" {
  capabilities = ["list"]
}
EOF
```

### Explanation

The first rule:

```hcl
path "secret/data/search-savor/*" {
  capabilities = ["read"]
}
```

allows ESO to read secret values under the Search & Savor path.

The second rule:

```hcl
path "secret/metadata/search-savor/*" {
  capabilities = ["list"]
}
```

allows listing metadata under that path.

We did not grant:

- `create`
- `update`
- `delete`
- `sudo`

This follows the principle of least privilege.

ESO only needs read access to synchronize the application secret.

---

# PART 3 — EXTERNAL SECRETS OPERATOR

## 10. Install External Secrets Operator

External Secrets Operator is a Kubernetes operator that retrieves secrets from external secret providers and creates Kubernetes Secret resources.

It supports multiple providers, including Vault.

### 10.1 Add the Helm repository

```bash
helm repo add external-secrets \
  https://charts.external-secrets.io
```

Update:

```bash
helm repo update
```

### 10.2 Create its namespace

```bash
kubectl create namespace external-secrets
```

### 10.3 Install ESO

```bash
helm install external-secrets \
  external-secrets/external-secrets \
  --namespace external-secrets \
  --set installCRDs=true
```

### Explanation

ESO includes:

- External Secrets controller.
- Certificate controller.
- Webhook.

The controller watches ExternalSecret and SecretStore resources.

The Custom Resource Definitions (CRDs) extend Kubernetes with resources such as:

```text
SecretStore
ClusterSecretStore
ExternalSecret
ClusterExternalSecret
```

Verify:

```bash
kubectl get pods -n external-secrets
```

Check the CRDs:

```bash
kubectl get crds | grep external-secrets
```

---

## 11. Create a Dedicated ServiceAccount for Vault Authentication

We created a dedicated ServiceAccount in the application namespace.

This is important because a namespaced SecretStore requires its referenced ServiceAccount to be in the same namespace.

Create it:

```bash
kubectl create serviceaccount eso-vault-auth \
  -n search-savor
```

The ServiceAccount is:

```text
eso-vault-auth
```

Namespace:

```text
search-savor
```

We use this ServiceAccount only as the identity ESO presents to Vault.

It is not the same as the ESO controller ServiceAccount.

---

## 12. Configure RBAC for ESO Token Requests

ESO needs permission to request a short-lived token for the `eso-vault-auth` ServiceAccount.

Kubernetes provides the TokenRequest API through the subresource:

```text
serviceaccounts/token
```

We granted the ESO controller permission to create tokens in the `search-savor` namespace.

File:

```text
k8s/eso-vault-rbac.yaml
```

Manifest:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: eso-vault-token-requester
  namespace: search-savor

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
  name: eso-vault-token-requester
  namespace: search-savor

subjects:
  - kind: ServiceAccount
    name: external-secrets
    namespace: external-secrets

roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: eso-vault-token-requester
```

Apply:

```bash
kubectl apply -f k8s/eso-vault-rbac.yaml
```

### Explanation

The Role grants:

```text
create serviceaccounts/token
```

within the `search-savor` namespace.

The RoleBinding gives that permission to:

```text
system:serviceaccount:external-secrets:external-secrets
```

This is the ESO controller identity.

The RoleBinding can refer to a ServiceAccount in a different namespace, while the Role itself remains namespaced.

### Important RBAC limitation

Kubernetes RBAC does not allow us to reliably restrict the `create` verb on this subresource to only one ServiceAccount using `resourceNames`.

Consequently, this Role allows the ESO controller to request tokens for ServiceAccounts in the `search-savor` namespace.

For this learning setup, we scoped the permission to the application namespace rather than granting it cluster-wide.

For a production environment, review ESO's supported authentication patterns and consider tighter isolation, separate namespaces, and admission controls.

### Verify the permission

```bash
kubectl auth can-i create serviceaccounts \
  --subresource=token \
  --as=system:serviceaccount:external-secrets:external-secrets \
  -n search-savor
```

Expected:

```text
yes
```

---

## 13. Create a Vault Kubernetes Authentication Role

Vault needs to know which Kubernetes ServiceAccount is allowed to authenticate and which Vault policy should be assigned to it.

We created the Vault role:

```text
eso-search-savor
```

Inside the Vault Pod:

```bash
vault write auth/kubernetes/role/eso-search-savor \
  bound_service_account_names=eso-vault-auth \
  bound_service_account_namespaces=search-savor \
  audience=vault \
  policies=search-savor-read \
  ttl=1h
```

### Explanation

| Parameter | Meaning |
|---|---|
| `bound_service_account_names` | Only the `eso-vault-auth` identity can authenticate |
| `bound_service_account_namespaces` | The identity must belong to `search-savor` |
| `audience` | Requires the token audience to be `vault` |
| `policies` | Grants the `search-savor-read` Vault policy |
| `ttl` | Vault-issued token lifetime is one hour |

The audience is important.

The Kubernetes token requested by ESO must have an audience that matches the Vault authentication role.

This helps ensure that the token is intended for Vault rather than being reused as a token for an unrelated service.

Verify the role:

```bash
vault read auth/kubernetes/role/eso-search-savor
```

---

# PART 4 — CONNECT ESO TO VAULT

## 14. Create the SecretStore

A SecretStore defines how ESO connects to an external secret provider.

We created:

```text
k8s/vault-secret-store.yaml
```

Manifest:

```yaml
apiVersion: external-secrets.io/v1
kind: SecretStore

metadata:
  name: vault-backend
  namespace: search-savor

spec:
  provider:
    vault:
      server: "http://vault.vault.svc.cluster.local:8200"

      path: "secret"

      version: "v2"

      auth:
        kubernetes:
          mountPath: "kubernetes"

          role: "eso-search-savor"

          serviceAccountRef:
            name: "eso-vault-auth"

            audiences:
              - "vault"
```

Apply:

```bash
kubectl apply -f k8s/vault-secret-store.yaml
```

Verify:

```bash
kubectl get secretstore vault-backend -n search-savor
```

Inspect:

```bash
kubectl describe secretstore vault-backend \
  -n search-savor
```

Expected condition:

```text
Type: Ready
Status: True
```

### Explanation of important fields

**server**

```yaml
server: "http://vault.vault.svc.cluster.local:8200"
```

This is the internal Kubernetes DNS address of Vault.

**path**

```yaml
path: "secret"
```

This identifies the Vault KV mount.

**version**

```yaml
version: "v2"
```

This tells ESO that the Vault mount uses KV Version 2.

**mountPath**

```yaml
mountPath: "kubernetes"
```

This is the Vault authentication mount path.

It corresponds to:

```text
auth/kubernetes/
```

**role**

```yaml
role: "eso-search-savor"
```

This is the Vault Kubernetes authentication role created earlier.

**serviceAccountRef**

```yaml
serviceAccountRef:
  name: "eso-vault-auth"
  audiences:
    - "vault"
```

ESO requests a short-lived Kubernetes token for this ServiceAccount.

The token is presented to Vault for authentication.

### Important namespace detail

For a namespaced SecretStore, the referenced ServiceAccount must be in the same namespace as the SecretStore.

That is why both resources are in:

```text
search-savor
```

The ESO controller itself can run in a different namespace.

---

# PART 5 — STORE THE API KEY IN VAULT

## 15. Store the YouTube API Key

We stored the API key in Vault under:

```text
secret/search-savor/youtube
```

The property name used inside Vault is:

```text
API_KEY
```

This is important because the property name inside Vault does not have to match the environment variable name used by FastAPI.

### Store the value

Authenticate to Vault using an administrative token, then store the API key.

For example:

```bash
vault kv put secret/search-savor/youtube \
  API_KEY="YOUR_API_KEY"
```

Replace the placeholder locally with your real API key.

Do not put a real key in Git, documentation, chat, or a shared terminal recording.

For interactive entry without placing the value directly in the command history, you can use a local Bash or Zsh shell:

```bash
read -s API_KEY
echo

vault