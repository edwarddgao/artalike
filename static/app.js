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

        // Handle the last row
        if (i === images.length - 1 && currentRow.length > 0) {
            rows.push(currentRow);
        }
    }

    return rows;
}

// Render Rows into HTML
function renderRows(rows, containerWidth) {
    const spacing = 8; // Space between images
    return rows.map(row => {
        const totalScaledWidth = row.reduce((sum, img) => sum + img.scaledWidth, 0);
        const totalSpacing = spacing * (row.length - 1);
        const scale = (containerWidth - totalSpacing) / totalScaledWidth;

        const imagesHtml = row.map(image => {
            const width = Math.floor(image.scaledWidth * scale);
            const height = Math.floor(250 * scale); // Maintain target height
            return `<div class="img-wrapper" style="width:${width}px;height:${height}px">
                <img src="${image.url}" width="${width}" height="${height}" loading="lazy" onclick="handleClick('${image.url}')" fetchpriority="high">
            </div>`;
        }).join('');

        return `<div class="row">${imagesHtml}</div>`;
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

// Infinite Scroll Event
window.addEventListener('scroll', debounce(() => {
    if ((window.innerHeight + window.scrollY) >= document.body.offsetHeight - 500) {
        // Near the bottom of the page
        showImages(currentImageUrl, false);
    }
}, 200));

// Initial Load
document.addEventListener('DOMContentLoaded', () => {
    showImages(currentImageUrl, true);
});