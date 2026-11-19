# actual converter website

Build with `npm ci` and `npm run build`. Upload the contents of `dist` into your hosting account's public web folder (InfinityFree uses `htdocs`). Use HTTPS. Relative asset paths support a subdirectory and any future domain. No backend or database is required.

The website converts HEIC, JPEG, PNG, GIF and WebP inputs to JPG, PNG and WebP. Video inputs can become MP4, WebM, GIF or still frames, subject to the browser FFmpeg codec build. Video conversion has a two-minute execution timeout. Image outputs use the first frame. The desktop app offers a wider format selection.

## File handling and limits

Selected media stays in browser memory. Conversion workers and canvas generate downloadable blobs. Clear all revokes output URLs and drops file references. Closing the tab releases the page's memory. No media upload endpoint, analytics or persistent file storage is implemented. Conversion libraries load from version-pinned jsDelivr URLs, and fonts load from Google Fonts. These providers receive ordinary web request metadata. Availability depends on those external services.

Limits use decimal MB. Images are capped at 20 MB, videos at 100 MB, batches at 10 files and 200 MB. Images are limited to 40 megapixels after decoding. This post-decode check cannot prevent all memory exhaustion from unusually large compressed images. Jobs run sequentially. Large HEIC files and video jobs may exceed a phone's available memory even within these limits. These are conservative initial product defaults, not an industry-wide standard.

## Architecture choices

| Option | Infrastructure | File lifecycle | Tradeoff |
| --- | --- | --- | --- |
| Browser conversion, implemented | Static hosting and CDN codec downloads | Local browser memory, explicit downloads | Low hosting cost and private media, device-dependent speed and codec coverage |
| Dedicated conversion server | Static frontend, HTTPS API, job queue, isolated FFmpeg/ImageMagick workers, private object storage | Short-lived signed upload URL, validate actual size and file signature, queue job, signed result URL, automatic deletion | Broad codec support and predictable performance, compute/storage/bandwidth costs and abuse controls |
| Hybrid | Browser path plus an optional server path | Local by default, explicit consent before a server upload | Handles large jobs but requires both systems and clear privacy UX |

For a server version, start with 20 MB images, 100 MB videos, 10 jobs per batch, one active job per anonymous session, a five-minute worker timeout, and a one-hour source/result retention window. Enforce byte limits in storage/API and workers, verify dimensions and duration before conversion, constrain worker CPU/memory/network, rate-limit submissions, use random private object keys, and delete failed and expired jobs. Show retention and upload consent before sending media. Anonymous download links must expire. Larger limits should follow load testing and a budget decision.

InfinityFree documents a 1 MB limit for HTML/PHP/JS and 10 MB for other hosted files, plus a separate PHP upload limit. This build's static files fit those limits. The roughly 32 MB FFmpeg core loads from jsDelivr. A server conversion service should run on infrastructure that supports native binaries and background workers.

Sources checked November 19, 2026

- https://forum.infinityfree.com/t/file-size-and-upload-limits/49308
- https://ffmpegwasm.netlify.app/docs/getting-started/usage/
- https://ffmpegwasm.netlify.app/docs/faq/
- https://alexcorvi.github.io/heic2any/

The app source is MIT licensed. Third-party conversion libraries and codecs retain their upstream licenses. Dependency versions are recorded in package-lock.json and pinned CDN URLs.
