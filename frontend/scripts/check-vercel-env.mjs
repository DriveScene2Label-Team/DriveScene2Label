// Only the Vercel build runs this check. Local Vite keeps using API_PROXY_TARGET.
const value = process.env.BACKEND_URL;
let valid = false;
try {
  const url = new URL(value);
  valid = url.protocol === 'https:' && url.origin === value
    && !url.username && !url.password
    && url.hostname !== 'localhost' && !url.hostname.endsWith('.localhost')
    && !url.hostname.startsWith('[') && !/^\d+\.\d+\.\d+\.\d+$/.test(url.hostname);
} catch {
  // Report the setting name, never its possibly sensitive value.
}
if (!valid) {
  console.error('Set BACKEND_URL to the authenticated public HTTPS origin, without a trailing slash, path, query or credentials. Use a public DNS hostname for this configuration.');
  process.exit(1);
}
if (new URL(value).hostname.endsWith('.devtunnels.ms')) {
  console.error('This routing configuration uses the Cognito-protected Cloudflare gateway. Restore the Microsoft request-header configuration before deploying a private Dev Tunnel origin.');
  process.exit(1);
}
console.log('BACKEND_URL format checked. Test gateway authentication and connectivity before deployment.');
