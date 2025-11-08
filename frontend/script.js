document.addEventListener('DOMContentLoaded', () => {
    // Pre-fill the host_url with the current location
    const hostUrlInput = document.getElementById('host_url');
    if (hostUrlInput) {
        hostUrlInput.value = window.location.origin;
    }

    if (navigator.share) {
        document.getElementById('shareBtn').style.display = 'inline-block';
    } else {
        document.getElementById('copyBtn').style.display = 'inline-block';
    }

    const configForm = document.getElementById('config-form');
    if (configForm) {
        configForm.addEventListener('submit', async (event) => {
            event.preventDefault();
            const spinner = document.querySelector('.spinner-border');
            spinner.style.display = 'inline-block';
            const manifestUrl = await getManifestUrl(true);
            if (manifestUrl) {
                window.location.href = manifestUrl;
            }
            spinner.style.display = 'none';
        });
    }

    document.getElementById('shareBtn').addEventListener('click', async (event) => {
        event.preventDefault();
        const manifestUrl = await getManifestUrl();
        if (manifestUrl) {
            try {
                await navigator.share({
                    title: 'EyePeaTeaVea Addon Manifest',
                    url: manifestUrl,
                });
            } catch (error) {
                displayFallbackUrl(manifestUrl);
                alert('Unable to use Share API. URL is ready to be copied manually.');
            }
        }
    });

    document.getElementById('copyBtn').addEventListener('click', async (event) => {
        event.preventDefault();
        const manifestUrl = await getManifestUrl();
        if (manifestUrl) {
            copyToClipboard(manifestUrl);
        }
    });

    document.getElementById('copyBtnResult').addEventListener('click', () => {
        const manifestUrl = document.getElementById('manifest_url').value;
        copyToClipboard(manifestUrl);
    });
});

async function getManifestUrl(isRedirect = false) {
    const m3uSources = document.getElementById('m3u_sources').value.split('\n').filter(url => url.trim() !== '');
    const parserScheduleCrontab = document.getElementById('parser_schedule_crontab').value;
    const hostUrl = document.getElementById('host_url').value;
    const addonPassword = document.getElementById('addon_password').value;

    const data = {
        m3u_sources: m3uSources,
        parser_schedule_crontab: parserScheduleCrontab,
        host_url: hostUrl,
        addon_password: addonPassword || null
    };

    try {
        const response = await fetch('/configure', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(data)
        });

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || 'An unknown error occurred.');
        }

        const result = await response.json();
        const secret_str = result.secret_str;
        
        let urlPrefix = window.location.protocol + "//";
        if (isRedirect) {
            urlPrefix = "stremio://";
        }

        const manifestUrl = `${urlPrefix}${hostUrl.replace(/^https?:\/\//, '')}/${secret_str}/manifest.json`;
        
        const resultDiv = document.getElementById('result');
        const manifestUrlInput = document.getElementById('manifest_url');
        manifestUrlInput.value = manifestUrl;
        resultDiv.style.display = 'block';

        generateQRCode(manifestUrl);

        return manifestUrl;

    } catch (error) {
        alert('Error: ' + error.message);
        return null;
    }
}

function displayFallbackUrl(url) {
    const resultDiv = document.getElementById('result');
    const manifestUrlInput = document.getElementById('manifest_url');
    manifestUrlInput.value = url;
    resultDiv.style.display = 'block';
    manifestUrlInput.focus();
    manifestUrlInput.select();
    generateQRCode(url);
}

function generateQRCode(url) {
    const qr = qrcode(0, 'L');
    qr.addData(url);
    qr.make();
    document.getElementById('qrcode').innerHTML = qr.createImgTag(4);
}

function copyToClipboard(text) {
    try {
        navigator.clipboard.writeText(text);
        alert('Manifest URL copied to clipboard.');
    } catch (error) {
        alert('Unable to access clipboard. URL is ready to be copied manually.');
    }
}