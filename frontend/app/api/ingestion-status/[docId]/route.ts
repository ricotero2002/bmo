import { NextResponse } from 'next/server';

export async function GET(
    request: Request,
    { params }: { params: { docId: string } }
) {
    const baseUrl = process.env.BACKEND_URL;
    const docId = params.docId;

    if (!baseUrl) {
        return NextResponse.json({ error: 'Missing Configuration' }, { status: 500 });
    }

    try {
        const response = await fetch(`${baseUrl}/api/ingestion-status/${docId}`, {
            method: 'GET',
        });

        const data = await response.json();
        return NextResponse.json(data, { status: response.status });
    } catch (error: any) {
        return NextResponse.json({ error: error.message }, { status: 500 });
    }
}
