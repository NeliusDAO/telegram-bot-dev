require('dotenv').config({ debug: false });

function getNetwork(phoneNumber) {
    // Normalize number: remove spaces, dashes, +234
    let number = phoneNumber.replace(/\s|-/g, '');

    if (number.startsWith('+234')) {
        number = '0' + number.slice(4);
    }

    const prefix = number.slice(0, 4);

    const networks = {
        MTN: ['0803', '0806', '0703', '0706', '0813', '0816', '0810', '0814', '0903', '0906', '0913'],
        Airtel: ['0802', '0808', '0708', '0812', '0701', '0902', '0907', '0901'],
        Glo: ['0805', '0807', '0705', '0815', '0811', '0905'],
        '9mobile': ['0809', '0817', '0818', '0909', '0908']
    };

    for (const [network, prefixes] of Object.entries(networks)) {
        if (prefixes.includes(prefix)) {
            return network;
        }
    }

    // return 'Unknown network';
}

// Provide a fetch fallback for Node environments without global fetch
let fetchFn = typeof fetch !== 'undefined' ? fetch : undefined;
if (!fetchFn) {
    try {
        fetchFn = require('node-fetch');
        if (fetchFn && fetchFn.default) fetchFn = fetchFn.default;
    } catch (e) {
        // node-fetch not installed; fetchFn will remain undefined
    }
}

async function getNetworkAPI(phoneNumber) {
    if (!fetchFn) {
        throw new Error('No fetch available. Use Node 18+ or install node-fetch.');
    }

    try {
        const base_url = 'http://apilayer.net/api/validate';
        const access_key = process.env.PHONEVERIFY_API_KEY || '';
        const params = new URLSearchParams({
            access_key,
            number: phoneNumber,
            country_code: 'NG'
        });

        const url = `${base_url}?${params.toString()}`;
        const response = await fetchFn(url, { method: 'GET' });

        if (!response.ok) {
            throw new Error(`HTTP error! Status: ${response.status}`);
        }

        const data = await response.json();

        // Extract carrier (robust against different API shapes) and return first word
        let carrierRaw = null;
        if (data) {
            if (typeof data.carrier === 'string') {
                carrierRaw = data.carrier;
            } else if (data.carrier && typeof data.carrier === 'object') {
                carrierRaw = data.carrier.name || data.carrier.provider || Object.values(data.carrier).find(v => typeof v === 'string');
            } else if (typeof data.provider === 'string') {
                carrierRaw = data.provider;
            } else if (typeof data.carrier_name === 'string') {
                carrierRaw = data.carrier_name;
            }
        }

        const carrierFirstWord = carrierRaw ? carrierRaw.trim().split(/\s+/)[0].toLowerCase() : null;
        return carrierFirstWord;
    } catch (error) {
        console.error('Error:', error);
        throw error;
    }
}

module.exports = { getNetwork, getNetworkAPI };

// Only run if called directly from CLI
if (require.main === module) {
    (async () => {
        try {
            const phoneNumber = process.argv[2];
            const carrier = await getNetworkAPI(phoneNumber);
            // Output JSON for easy parsing from Python
            console.log(JSON.stringify({ carrier }));
        } catch (e) {
            // error already logged inside getNetworkAPI
        }
    })();
}
