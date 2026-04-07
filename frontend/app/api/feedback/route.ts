import { NextResponse } from 'next/server';

export async function POST(request: Request) {
    const baseUrl = process.env.BACKEND_URL;

    if (!baseUrl) {
        console.error('CRITICAL ERROR: BACKEND_URL environment variable is missing.');
        return NextResponse.json({ error: 'Internal Server Error: Missing Configuration' }, { status: 500 });
    }

    try {
        const body = await request.json();

        const response = await fetch(`${baseUrl}/api/feedback`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(body),
        });
        
        if (!response.ok) {
            return NextResponse.json({ error: 'Failed to send feedback to backend' }, { status: response.status });
        }
        
        const data = await response.json();
        return NextResponse.json(data);
    } catch (error: any) {
        console.error('Error sending feedback:', error);
        return NextResponse.json({ 
            error: 'Internal Server Error', 
            details: error.message || String(error)
        }, { status: 500 });
    }
}
