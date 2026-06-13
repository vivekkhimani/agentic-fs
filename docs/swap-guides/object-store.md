# Swap guide: object store

The object store is where document bytes live. agentic-fs talks to it through one
small contract — `afs_core.contracts.ObjectStore` — so you can run it on whatever
blob storage you already have.

## You probably don't need to write any code

The default `S3ObjectStore` speaks plain S3, so **any S3-compatible service is a
config change, not a code change**. Point the endpoint at it:

| Storage | `AFS_S3_ENDPOINT_URL` | Notes |
|---|---|---|
| AWS S3 | *(unset)* | the default |
| MinIO (local dev) | `http://localhost:9000` | `AWS_ACCESS_KEY_ID`/`SECRET` = your MinIO creds |
| Cloudflare R2 | `https://<account>.r2.cloudflarestorage.com` | R2 is S3-compatible; use an R2 API token |
| Wasabi / Backblaze B2 | the provider's S3 endpoint | same |

```bash
export AFS_OBJECT_STORE_BACKEND=s3
export AFS_S3_ENDPOINT_URL=https://<account>.r2.cloudflarestorage.com
export AFS_DATA_BUCKET=my-bucket
# standard AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY for the chosen provider
```

That's the whole swap for S3-compatible storage.

## Writing a non-S3 backend

If your storage isn't S3-shaped (say a custom blob service), implement the
contract and register it:

1. **Implement** `ObjectStore` (8 async methods: `get` with ranges, `put`,
   `delete`, `delete_prefix`, `stat`, `list` with opaque-cursor pagination,
   `presigned_put`, `presigned_get`).
2. **Certify** it — subclass the conformance kit and make it green:
   ```python
   from afs_core.testing import ObjectStoreConformance

   class TestMyStore(ObjectStoreConformance):
       @pytest.fixture
       def store(self):
           return MyStore(...)
   ```
3. **Register** an entry point and build function `build(settings) -> ObjectStore`:
   ```toml
   # your package's pyproject.toml
   [project.entry-points."afs.object_stores"]
   myblob = "mypkg.store:build"
   ```
4. **Select** it: `pip install your-package` and set
   `AFS_OBJECT_STORE_BACKEND=myblob`.

The server never imports your package directly — it discovers it through the
`afs.object_stores` entry-point group. No fork.

## Contract reference

`afs_core/contracts/objects.py`. Certified by
`afs_core.testing.ObjectStoreConformance`. The reference impls are
`afs_server.stores.objects_s3.S3ObjectStore` (production) and
`afs_core.testing.InMemoryObjectStore` (tests).
