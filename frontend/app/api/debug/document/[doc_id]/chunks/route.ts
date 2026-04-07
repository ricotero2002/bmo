import { NextResponse } from 'next/server';

export async function GET(
    request: Request,
    { params }: { params: Promise<{ doc_id: string }> }
) {
    const baseUrl = process.env.BACKEND_URL;
    const resolvedParams = await params;

    if (!baseUrl) {
        console.error('CRITICAL ERROR: BACKEND_URL environment variable is missing.');
        return NextResponse.json({ error: 'Internal Server Error: Missing Configuration' }, { status: 500 });
    }

    try {
        const response = await fetch(`${baseUrl}/api/debug/document/${resolvedParams.doc_id}/chunks`, {
            cache: 'no-store'
        });

        if (!response.ok) {
            return NextResponse.json({ error: 'Failed to fetch messages from backend' }, { status: response.status });
        }

        const data = await response.json();
        return NextResponse.json(data);
    } catch (error: any) {
        console.error('Error fetching messages:', error);
        return NextResponse.json({
            error: 'Internal Server Error',
            details: error.message || String(error)
        }, { status: 500 });
    }
}
