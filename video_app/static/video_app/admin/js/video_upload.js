/**
 * Video Upload Progress Handler for Django Admin
 * Shows loading animation and upload progress when submitting video forms
 */
(function() {
    'use strict';

    // Create overlay HTML
    function createOverlay() {
        const overlay = document.createElement('div');
        overlay.className = 'video-upload-overlay';
        overlay.id = 'video-upload-overlay';
        overlay.innerHTML = `
            <div class="video-upload-spinner"></div>
            <div class="video-upload-text" id="upload-status-text">Uploading video...</div>
            <div class="video-upload-progress" id="upload-progress-percent">0%</div>
            <div class="video-upload-progress-bar">
                <div class="video-upload-progress-bar-fill" id="upload-progress-bar"></div>
            </div>
            <div class="video-upload-details" id="upload-details"></div>
        `;
        document.body.appendChild(overlay);
        return overlay;
    }

    // Format bytes to human readable
    function formatBytes(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }

    // Format time remaining
    function formatTime(seconds) {
        if (seconds < 60) return Math.round(seconds) + 's remaining';
        if (seconds < 3600) return Math.round(seconds / 60) + 'm remaining';
        return Math.round(seconds / 3600) + 'h remaining';
    }

    // Initialize when DOM is ready
    document.addEventListener('DOMContentLoaded', function() {
        const form = document.querySelector('#video_form, form[enctype="multipart/form-data"]');
        if (!form) return;

        const overlay = createOverlay();
        const statusText = document.getElementById('upload-status-text');
        const progressPercent = document.getElementById('upload-progress-percent');
        const progressBar = document.getElementById('upload-progress-bar');
        const uploadDetails = document.getElementById('upload-details');

        // Check if there's a video file input
        const videoFileInput = form.querySelector('input[type="file"][name="video_file"]');
        if (!videoFileInput) return;

        form.addEventListener('submit', function(e) {
            const file = videoFileInput.files[0];
            
            // Only show progress for actual file uploads
            if (!file) {
                // No file selected, just show simple loading
                overlay.classList.add('active');
                statusText.textContent = 'Saving...';
                progressPercent.textContent = '';
                progressBar.style.width = '100%';
                uploadDetails.textContent = '';
                return;
            }

            // Prevent default form submission
            e.preventDefault();

            // Show overlay
            overlay.classList.add('active');
            statusText.textContent = 'Uploading video...';
            uploadDetails.textContent = formatBytes(file.size);

            // Create FormData from form
            const formData = new FormData(form);

            // Create XMLHttpRequest for progress tracking
            const xhr = new XMLHttpRequest();
            let startTime = Date.now();

            xhr.upload.addEventListener('progress', function(e) {
                if (e.lengthComputable) {
                    const percent = Math.round((e.loaded / e.total) * 100);
                    progressPercent.textContent = percent + '%';
                    progressBar.style.width = percent + '%';

                    // Calculate speed and ETA
                    const elapsed = (Date.now() - startTime) / 1000;
                    const speed = e.loaded / elapsed;
                    const remaining = (e.total - e.loaded) / speed;

                    uploadDetails.textContent = formatBytes(e.loaded) + ' / ' + formatBytes(e.total) + 
                        ' • ' + formatBytes(speed) + '/s' +
                        (remaining > 0 ? ' • ' + formatTime(remaining) : '');

                    if (percent === 100) {
                        statusText.textContent = 'Processing video...';
                        uploadDetails.textContent = 'Fetching metadata and creating preview...';
                    }
                }
            });

            xhr.addEventListener('load', function() {
                if (xhr.status >= 200 && xhr.status < 400) {
                    statusText.textContent = 'Complete!';
                    progressPercent.textContent = '✓';
                    uploadDetails.textContent = 'Redirecting...';
                    
                    // Redirect to the response URL or parse redirect from response
                    setTimeout(function() {
                        // Try to follow redirect from response
                        if (xhr.responseURL) {
                            window.location.href = xhr.responseURL;
                        } else {
                            // Fallback: reload or go to changelist
                            window.location.reload();
                        }
                    }, 500);
                } else {
                    // Error occurred
                    overlay.classList.remove('active');
                    // Create a temporary form to resubmit and show Django's error
                    const tempDiv = document.createElement('div');
                    tempDiv.innerHTML = xhr.responseText;
                    document.body.innerHTML = xhr.responseText;
                }
            });

            xhr.addEventListener('error', function() {
                statusText.textContent = 'Upload failed!';
                progressPercent.textContent = '✗';
                uploadDetails.textContent = 'Network error. Please try again.';
                setTimeout(function() {
                    overlay.classList.remove('active');
                }, 2000);
            });

            xhr.addEventListener('abort', function() {
                overlay.classList.remove('active');
            });

            // Open and send request
            xhr.open('POST', form.action || window.location.href, true);
            xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');
            xhr.send(formData);
        });
    });
})();
