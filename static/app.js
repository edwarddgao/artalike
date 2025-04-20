// static/app.js

const API_BASE_URL = window.location.hostname === 'localhost' ? 'http://localhost:8000/api' : '/api';

const cache = new Map();
const grid = document.getElementById('grid');
const loader = document.getElementById('loader');
let currentRequest = null;
let images = [];

// State Variables
let currentOffset = 0;
let isLoading = false;
let hasMore = true;
const limit = 20;
let currentImageUrl = new URL(window.location.href).searchParams.get('image') || null;
let isPrefetching = false; // Track if we're prefetching the next batch
let prefetchThreshold = 0.5; // Load more when 50% through current content

// Debounce Function
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// Fetch Images with Pagination
async function fetchImages(imageUrl = null, offset = 0) {
    const cacheKey = (imageUrl || 'random') + '_' + offset;
    if (cache.has(cacheKey)) {
        return cache.get(cacheKey);
    }

    const endpoint = imageUrl ? 
        `/search?url=${encodeURIComponent(imageUrl)}&offset=${offset}&limit=${limit}` : 
        `/random?offset=${offset}&limit=${limit}`;

    try {
        const controller = new AbortController();
        currentRequest?.abort();
        currentRequest = controller;

        const response = await fetch(`${API_BASE_URL}${endpoint}`, {
            credentials: 'include',
            headers: { 'Accept': 'application/json' },
            signal: controller.signal
        });

        if (!response.ok) throw new Error('Network response was not ok');
        const data = await response.json();
        cache.set(cacheKey, data.results);
        return data.results;
    } catch (error) {
        if (error.name === 'AbortError') return null;
        console.error('Fetch error:', error);
        return null;
    }
}

// Layout Images into Rows
async function layoutImages(images, containerWidth) {
    const targetHeight = 250; // Desired row height
    const spacing = 8; // Space between images
    const rows = [];
    let currentRow = [];
    let rowWidth = 0;
    const minImagesPerRow = 3; // Minimum images desired per row

    for (let i = 0; i < images.length; i++) {
        const image = images[i];
        if (!image) continue;

        const aspectRatio = image.width / image.height;
        const scaledWidth = targetHeight * aspectRatio;

        if (rowWidth + scaledWidth + spacing * currentRow.length <= containerWidth || currentRow.length === 0) {
            currentRow.push({ ...image, scaledWidth });
            rowWidth += scaledWidth;
        } else {
            rows.push([...currentRow]);
            currentRow = [{ ...image, scaledWidth }];
            rowWidth = scaledWidth;
        }

        // Handle the last image - ensure the final row is pushed
        if (i === images.length - 1 && currentRow.length > 0) {
            rows.push(currentRow);
            currentRow = []; // Clear current row as it's now in rows
        }
    }

    // Post-processing: Merge last row if it has less than minImagesPerRow images
    if (rows.length > 1 && rows[rows.length - 1].length < minImagesPerRow) {
        const lastRowImages = rows.pop(); // Remove the last row
        rows[rows.length - 1].push(...lastRowImages); // Append its images to the second-to-last row
    }

    return rows;
}

// Intersection Observer for Lazy Loading
let observer;
const lazyLoadImage = (entries, observer) => {
    entries.forEach(entry => {
        if (entry.isIntersecting) {
            const img = entry.target;
            const fullSrc = img.dataset.src;
            if (fullSrc) {
                img.src = fullSrc; // Swap src to full resolution
                img.classList.remove('lazy'); // Optional: remove lazy class
                // Optional: Add loaded class for styling (e.g., fade-in)
                img.classList.add('loaded'); 
                observer.unobserve(img); // Stop observing once loaded
            }
        }
    });
};

// Initialize Observer (consider rootMargin for earlier loading)
observer = new IntersectionObserver(lazyLoadImage, {
    rootMargin: '0px 0px 200px 0px' // Load images 200px before they enter viewport
});

// Prefetch Observer - load more content when a prefetch sentinel comes into view
let prefetchObserver;
const prefetchSentinelId = 'prefetch-sentinel';

const prefetchCallback = (entries, observer) => {
    entries.forEach(entry => {
        if (entry.isIntersecting && !isLoading && hasMore && !isPrefetching) {
            // When the sentinel is visible, prefetch the next batch
            prefetchNextBatch();
        }
    });
};

prefetchObserver = new IntersectionObserver(prefetchCallback, {
    rootMargin: '0px 0px 1000px 0px' // Prefetch when 1000px from the bottom
});

// Create and add prefetch sentinel
function addPrefetchSentinel() {
    // Remove existing sentinel if it exists
    let existingSentinel = document.getElementById(prefetchSentinelId);
    if (existingSentinel) {
        existingSentinel.remove();
    }
    
    // Create new sentinel
    const sentinel = document.createElement('div');
    sentinel.id = prefetchSentinelId;
    sentinel.style.height = '1px';
    sentinel.style.width = '100%';
    sentinel.style.position = 'relative';
    sentinel.style.top = '-1000px'; // Position it 1000px above the bottom of content
    grid.appendChild(sentinel);
    
    // Start observing the sentinel
    prefetchObserver.observe(sentinel);
}

// Prefetch next batch of images
async function prefetchNextBatch() {
    if (isLoading || !hasMore || isPrefetching) return;
    
    isPrefetching = true;
    
    // Prefetch the next batch of images
    await fetchImages(currentImageUrl, currentOffset);
    
    isPrefetching = false;
}

// Render Rows into HTML
function renderRows(rows, containerWidth) {
    const spacing = 8; // Space between images
    return rows.map((row, rowIndex) => {
        const totalScaledWidth = row.reduce((sum, img) => sum + img.scaledWidth, 0);
        const totalSpacing = spacing * (row.length - 1);
        const scale = (containerWidth - totalSpacing) / totalScaledWidth;

        const imagesHtml = row.map(image => {
            const width = Math.floor(image.scaledWidth * scale);
            const height = Math.floor(250 * scale); // Maintain target height
            // Use thumbnail_url for initial src, store full url in data-src
            const initialSrc = image.thumbnail_url || image.url; // Fallback to full url if thumbnail missing
            const fullSrc = image.url;

            return `<div class="img-wrapper" style="width:${width}px;height:${height}px">
                <img 
                    src="${initialSrc}" 
                    data-src="${fullSrc}" 
                    width="${width}" 
                    height="${height}" 
                    class="lazy" 
                    onclick="handleClick('${image.url}')"
                >
            </div>`;
        }).join('');

        // Add a unique ID to each new row to help select images for observation
        return `<div class="row" id="row-${currentOffset + rowIndex}">${imagesHtml}</div>`; 
    }).join('');
}

// Show Images Function
async function showImages(imageUrl = null, reset = true) {
    if (reset) {
        images = [];
        grid.innerHTML = '';
        currentOffset = 0;
        hasMore = true;
        currentImageUrl = imageUrl;
        window.scrollTo(0, 0); // Scroll to top on new search
    }
    if (isLoading || !hasMore) return;
    isLoading = true;
    loader.style.display = 'block';

    const rowStartOffset = currentOffset; // Remember offset before fetching new images

    const newImages = await fetchImages(imageUrl, currentOffset);
    isLoading = false;
    loader.style.display = 'none';

    if (!newImages || newImages.length === 0) {
        hasMore = false;
        return;
    }

    // Update Offset
    currentOffset += newImages.length;

    // Layout and Render New Rows
    const containerWidth = grid.offsetWidth;
    const rows = await layoutImages(newImages.filter(Boolean), containerWidth);
    const newRowsHtml = renderRows(rows, containerWidth);

    // Append New Rows to Grid
    grid.insertAdjacentHTML('beforeend', newRowsHtml);

    // Observe newly added images
    const newImagesSelector = rows.map((_, i) => `#row-${rowStartOffset + i} img.lazy`).join(', ');
    if (newImagesSelector) { 
        document.querySelectorAll(newImagesSelector).forEach(img => {
            observer.observe(img);
        });
    }
    
    // Add prefetch sentinel after adding new content
    addPrefetchSentinel();
    
    // If we're less than halfway through our content, preload the next batch immediately
    if (currentOffset < limit * 2 && hasMore) {
        prefetchNextBatch();
    }
}

// Handle Image Click (Search Similar)
function handleClick(imageUrl) {
    history.pushState({ imageUrl }, '', `?image=${encodeURIComponent(imageUrl)}`);
    showImages(imageUrl, true);
}

// Handle Back/Forward Navigation
window.addEventListener('popstate', e => showImages(e.state?.imageUrl));

// Debounced Resize Event
const debouncedResize = debounce(() => {
    showImages(currentImageUrl, true);
}, 250);
window.addEventListener('resize', debouncedResize);

// Scroll event handler - more aggressive than before
window.addEventListener('scroll', () => {
    const scrollPosition = window.scrollY + window.innerHeight;
    const docHeight = document.body.offsetHeight;
    const scrollPercentage = scrollPosition / docHeight;
    
    // If we're getting close to the bottom (within 30%), load more immediately
    if (scrollPercentage > 0.7 && !isLoading && hasMore) {
        showImages(currentImageUrl, false);
    }
});

// Initial Load
document.addEventListener('DOMContentLoaded', () => {
    showImages(currentImageUrl, true);
});