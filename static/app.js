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
let currentImageUrl = null; // Store the active search URL or null for random
let isPrefetching = false;
let prefetchThreshold = 0.5;

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

// Layout Images into Rows (No Single-Image Rows constraint)
function layoutImages(images, containerWidth) {
    const targetHeight = 250; // Desired row height
    const spacing = 8; // Space between images
    const rows = [];
    let currentRow = [];
    let rowWidth = 0;

    // --- Pass 1: Initial Row Creation --- 
    for (let i = 0; i < images.length; i++) {
        const image = images[i];
        if (!image) continue;

        const aspectRatio = image.width / image.height;
        const scaledWidth = targetHeight * aspectRatio;

        // Check if adding the image exceeds the container width or if it's the first image
        if (currentRow.length === 0 || (rowWidth + scaledWidth + spacing * currentRow.length <= containerWidth)) {
            currentRow.push({ ...image, scaledWidth });
            rowWidth += scaledWidth;
        } else {
            // Current row is full, push it and start a new one
            rows.push([...currentRow]);
            currentRow = [{ ...image, scaledWidth }];
            rowWidth = scaledWidth;
        }
    }
    // Push the last remaining row if it has images
    if (currentRow.length > 0) {
        rows.push(currentRow);
    }

    // --- Pass 2: Merge Single-Image Rows (Iterate Backwards) --- 
    if (rows.length <= 1) {
        return rows; // Nothing to merge if 0 or 1 row
    }

    for (let i = rows.length - 1; i > 0; i--) { // Iterate down to index 1
        if (rows[i].length === 1) { // Check if the current row has exactly one image
            console.log(`Merging single-image row ${i} into previous row.`);
            // Merge the single image into the previous row
            rows[i - 1].push(...rows[i]);
            // Remove the single-image row
            rows.splice(i, 1); 
        }
    }
    // Note: The very first row (rows[0]) is allowed to have a single image
    // if the total number of images necessitates it (e.g., only 1 image in the batch).

    return rows;
}

// Simplified function to upgrade thumbnails to full images after they load
function setupImageUpgrading() {
    // Use event delegation to handle all images, including ones added dynamically
    grid.addEventListener('load', function(e) {
        // Check if the loaded element is an image with data-fullsrc
        if (e.target.tagName === 'IMG' && e.target.dataset.fullsrc) {
            const img = e.target;
            const fullSrc = img.dataset.fullsrc;
            
            // Only replace if we haven't already loaded the full image
            if (img.currentSrc !== fullSrc) {
                img.src = fullSrc;
                img.classList.add('loaded'); // Optional: add loaded class for styling
                
                // Clean up to avoid repeated loads
                delete img.dataset.fullsrc;
            }
        }
    }, true); // Use capture to get the events before they reach the target
}

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
function renderRows(rows, containerWidth, isFirstBatch = false) {
    const spacing = 8; // Space between images
    return rows.map((row, rowIndex) => {
        const totalScaledWidth = row.reduce((sum, img) => sum + img.scaledWidth, 0);
        const totalSpacing = spacing * (row.length - 1);
        const scale = (containerWidth - totalSpacing) / totalScaledWidth;

        const imagesHtml = row.map(image => {
            const width = Math.floor(image.scaledWidth * scale);
            const height = Math.floor(250 * scale); // Maintain target height
            const src = image.thumbnail_url || image.url;
            // Load first batch eagerly, lazy load subsequent batches
            const loadingAttr = isFirstBatch ? 'eager' : 'lazy';

            return `<div class="img-wrapper"
                         style="width:${width}px;height:${height}px"
                         data-scaled-width="${image.scaledWidth}">
                <img
                    src="${src}"
                    loading="${loadingAttr}"
                    width="${width}"
                    height="${height}"
                    onclick="handleClick('${image.url}')"
                >
            </div>`;
        }).join('');

        // Add a unique ID to each new row to help select images for observation
        return `<div class="row" id="row-${currentOffset + rowIndex}">${imagesHtml}</div>`;
    }).join('');
}

// Show Images Function
async function showImages(imageUrl, reset = true) {
    // If it's a reset, clear everything and set the new state
    if (reset) {
        grid.innerHTML = '';
        currentOffset = 0;
        hasMore = true;
        currentImageUrl = imageUrl; // Update the current view type
        window.scrollTo(0, 0); // Scroll to top only on explicit reset
        // Stop observing any existing sentinels
        let existingSentinel = document.getElementById(prefetchSentinelId);
        if (existingSentinel) prefetchObserver.unobserve(existingSentinel);
    }

    if (isLoading || !hasMore) return;
    isLoading = true;
    loader.style.display = 'block';

    const rowStartOffset = currentOffset; // Remember offset before fetching new images

    // Fetch images for the current state (imageUrl) and currentOffset
    const newImages = await fetchImages(currentImageUrl, currentOffset);

    if (!newImages || newImages.length === 0) {
        hasMore = false;
        isLoading = false;
        loader.style.display = 'none';
        return;
    }

    // Update Offset for the *next* fetch
    currentOffset += newImages.length;

    // Layout and Render New Rows
    const containerWidth = grid.offsetWidth;
    const rows = layoutImages(newImages.filter(Boolean), containerWidth);
    const newRowsHtml = renderRows(rows, containerWidth, reset);

    // Append New Rows to Grid
    grid.insertAdjacentHTML('beforeend', newRowsHtml);
    
    addPrefetchSentinel();
    
    isLoading = false;
    loader.style.display = 'none';
}

// Handle Image Click (Search Similar)
function handleClick(imageUrl) {
    // 1. Save the current state (view type, offset, scroll position, AND the image being clicked)
    history.replaceState({
        imageUrl: currentImageUrl, // null for random, or the search URL if clicking from search results
        offset: currentOffset,
        scrollY: window.scrollY,
        clickedImageUrl: imageUrl // Store the URL of the image triggering the search
    }, '');

    // 2. Push the new state for the search view
    history.pushState({ imageUrl: imageUrl }, '', `?image=${encodeURIComponent(imageUrl)}`);

    // 3. Show search results (resets grid, offset, sets currentImageUrl)
    showImages(imageUrl, true);
}

// --- Modified popstate handler (Concurrent Fetching + Targeted Scroll Restore) ---
window.addEventListener('popstate', async e => { // Still async
    const state = e.state || {}; // Ensure state is an object
    const targetImageUrl = state.imageUrl; // URL to restore (null for random)
    const savedOffset = state.offset || 0;
    const savedScrollY = state.scrollY;
    const previouslyClickedImageUrl = state.clickedImageUrl; // Get the URL that was clicked to navigate away

    console.log("Popstate triggered. Restoring state:", state);

    // Prevent scroll/prefetch triggers during restore
    isLoading = true; 
    loader.style.display = 'block';
    grid.innerHTML = ''; // Clear the grid immediately

    // --- State Restoration Logic ---
    currentImageUrl = targetImageUrl; // Set the mode (random or search)
    currentOffset = 0; // Will be updated after fetching
    hasMore = true; // Assume true initially

    const numBatchesNeeded = Math.ceil(savedOffset / limit);
    console.log(`Need to restore ${numBatchesNeeded} batches to reach offset ${savedOffset}`);

    if (numBatchesNeeded <= 0 && !targetImageUrl) { // Handle case of going back to empty initial random state
        console.log("No batches needed for restore, loading initial view.");
        await showImages(null, true); // Perform a clean initial load of random
    } else if (numBatchesNeeded <=0 && targetImageUrl) { // Handle case of going back to initial search state (only first batch)
        console.log("Restoring initial search view.");
        await showImages(targetImageUrl, true);
    } else { // Restore multiple batches
        // Create fetch promises for all needed batches
        const fetchPromises = [];
        for (let i = 0; i < numBatchesNeeded; i++) {
            fetchPromises.push(fetchImages(currentImageUrl, i * limit));
        }

        try {
            const allResultsArrays = await Promise.all(fetchPromises);
            const allImages = allResultsArrays.flat().filter(Boolean);

            if (allImages.length === 0) {
                console.log("No images found during state restoration.");
                hasMore = false;
            } else {
                // Layout and Render All Fetched Images at Once
                const containerWidth = grid.offsetWidth;
                // *** Crucially use renderRows which contains the short-row logic ***
                const rows = layoutImages(allImages, containerWidth);
                const allRowsHtml = renderRows(rows, containerWidth, true);
                grid.innerHTML = allRowsHtml; // Replace content in one go

                // Update state *after* rendering
                currentOffset = allImages.length; // Set offset to total loaded
                const lastBatch = allResultsArrays[allResultsArrays.length - 1];
                if (!lastBatch || lastBatch.length < limit) {
                    hasMore = false;
                }
                
                // Add prefetch sentinel now that content is loaded
                addPrefetchSentinel();
            }
        } catch (error) {
            console.error("Error during concurrent fetch for state restoration:", error);
            hasMore = false; // Assume error means no more content
        }
    }
    // --- Scroll Restoration --- 
    isLoading = false;
    loader.style.display = 'none';
    console.log("State restoration content loaded.");

    // Prioritize scrolling to the clicked image if possible
    let scrollTargetRestored = false;
    if (previouslyClickedImageUrl) {
        // Need slight delay for browser to render the new grid content
        requestAnimationFrame(() => { 
            const targetElement = grid.querySelector(`img[data-fullsrc=\"${previouslyClickedImageUrl}\"]`);
            if (targetElement) {
                console.log(`Scrolling to previously clicked image: ${previouslyClickedImageUrl}`);
                targetElement.scrollIntoView({ block: 'center', behavior: 'auto' });
                scrollTargetRestored = true;
            } else {
                console.log("Previously clicked image not found in restored view.");
            }
            // If target wasn't found, fall back to scrollY restore *outside* this animation frame
            if (!scrollTargetRestored && savedScrollY !== undefined) {
                 console.log(`Falling back to restoring scrollY: ${savedScrollY}`);
                 window.scrollTo(0, savedScrollY);
            } else if (!scrollTargetRestored) {
                 console.log("No scroll target, scrolling to top.");
                 window.scrollTo(0, 0);
            }
        });
    } else if (savedScrollY !== undefined) {
        // If no specific image was clicked (e.g., back from external site), restore Y
         console.log(`Restoring scrollY: ${savedScrollY}`);
         requestAnimationFrame(() => { 
             window.scrollTo(0, savedScrollY);
         });
    } else {
        // Default to top if no scroll info
        console.log("No scroll info, scrolling to top.");
         requestAnimationFrame(() => { 
             window.scrollTo(0, 0);
         });
    }
});

// Modified Scroll event handler - now triggers showImages directly
window.addEventListener('scroll', () => {
    // No debounce needed here for responsiveness
    const scrollPosition = window.scrollY + window.innerHeight;
    const docHeight = document.body.offsetHeight;
    const scrollPercentage = scrollPosition / docHeight;
    
    // If we're getting close to the bottom, load more immediately
    // Ensure not already loading and there's potentially more content
    if (scrollPercentage > 0.7 && !isLoading && hasMore) {
        showImages(currentImageUrl, false); // reset=false to append
    }
});

// Initial Load
document.addEventListener('DOMContentLoaded', () => {
    // Set up the image upgrading system
    setupImageUpgrading();
    
    // Check if URL has an image search parameter on initial load
    const initialSearchUrl = new URL(window.location.href).searchParams.get('image');
    if (initialSearchUrl) {
        // Store initial state correctly
        history.replaceState({ imageUrl: initialSearchUrl }, '', window.location.href);
        showImages(initialSearchUrl, true); 
    } else {
        // Store initial random state
        history.replaceState({ imageUrl: null, offset: 0, scrollY: 0 }, '');
        showImages(null, true); // Load initial random images
    }
});