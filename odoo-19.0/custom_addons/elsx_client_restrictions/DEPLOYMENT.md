# Deployment

The normal container startup upgrades this addon behind the encrypted-backup
release gate. It restores native Settings metadata, removes obsolete helper
groups and generated assets, and leaves business records unchanged.

After deployment, verify:

1. Settings and Users open without an Apps password.
2. Apps opens the password form.
3. An incorrect password cannot load Apps.
4. The configured password opens native Apps and normal module operations work.
