# Security

Medical information requires careful handling.

Never commit:

```text
.env
API keys
Database passwords
Private credentials
Production secrets
```

If a credential is exposed:

1. Revoke it immediately.
2. Rotate the credential.
3. Update deployment secrets.
4. Review repository history if necessary.

For production environments, consider:

* HTTPS
* strong authentication secrets
* managed PostgreSQL
* secret management
* restricted Kubernetes permissions
* protected monitoring endpoints
* controlled document storage
* appropriate access controls
* audit logging

---
