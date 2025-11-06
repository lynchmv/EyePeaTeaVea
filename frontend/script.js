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
            const manifestUrl = await getManifestUrl(true);
            if (manifestUrl) {
                window.location.href = manifestUrl;
            }
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
            try {
                await navigator.clipboard.writeText(manifestUrl);
                alert('Manifest URL copied to clipboard.');
            } catch (error) {
                displayFallbackUrl(manifestUrl);
                alert('Unable to access clipboard. URL is ready to be copied manually.');
            }
        }
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
        const manifestUrlTextarea = document.getElementById('manifest_url');
        manifestUrlTextarea.value = manifestUrl;
        resultDiv.classList.remove('hidden');

        return manifestUrl;

    } catch (error) {
        alert('Error: ' + error.message);
        return null;
    }
}

function displayFallbackUrl(url) {
    const resultDiv = document.getElementById('result');
    const manifestUrlTextarea = document.getElementById('manifest_url');
    manifestUrlTextarea.value = url;
    resultDiv.classList.remove('hidden');
    manifestUrlTextarea.focus();
    manifestUrlTextarea.select();
}