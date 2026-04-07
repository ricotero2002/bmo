"use client";

import React, { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Trash2, RefreshCw, Upload, File, Loader2, X, Calendar, Eye } from "lucide-react";
import { fetchDocuments, checkIngestionStatus, deleteDocument, uploadDocument, getDocumentChunks } from "@/services/api";

interface DocumentManagerProps {
  userId: string;
  onClose: () => void;
}

interface DocumentJob {
  doc_id: string;
  source_path: string;
  status: string;
  created_at: string;
}

export default function DocumentManager({ userId, onClose }: DocumentManagerProps) {
  const queryClient = useQueryClient();
  const [uploadStatus, setUploadStatus] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [documentDate, setDocumentDate] = useState("");
  const [selectedChunks, setSelectedChunks] = useState<any[] | null>(null);

  // Fetch documents list
  const { data, isLoading, isError, refetch } = useQuery<{ documents: DocumentJob[] }>({
    queryKey: ["documents", userId],
    queryFn: async () => fetchDocuments(userId),
    enabled: !!userId,
  });

  const documents = data?.documents || [];
  
  const filteredDocuments = documents.filter(doc => 
    doc.source_path.toLowerCase().includes(searchQuery.toLowerCase()) || 
    doc.doc_id.toLowerCase().includes(searchQuery.toLowerCase())
  );

  // Check specific status
  const checkStatusMutation = useMutation({
    mutationFn: async (docId: string) => checkIngestionStatus(docId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["documents", userId] });
    },
  });

  // Delete Document
  const deleteMutation = useMutation({
    mutationFn: async (docId: string) => deleteDocument(docId, userId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["documents", userId] });
    },
  });

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setIsUploading(true);
    setUploadStatus(`Uploading: ${file.name}...`);

    const formData = new FormData();
    formData.append('file', file);
    if (userId) formData.append('user_id', userId);

    try {
      const res = await uploadDocument(file, userId, documentDate);
      const resData = await res.json();

      if (res.ok) {
        setUploadStatus(`'${file.name}' processed successfully.`);
        setTimeout(() => setUploadStatus(null), 3000);
        queryClient.invalidateQueries({ queryKey: ["documents", userId] });
      } else {
        setUploadStatus(`Error uploading file: ${resData.error || 'Unknown error'}`);
        setTimeout(() => setUploadStatus(null), 5000);
      }
    } catch (error) {
      console.error("Upload error:", error);
      setUploadStatus("Network error during upload.");
      setTimeout(() => setUploadStatus(null), 5000);
    } finally {
      setIsUploading(false);
      // reset input value
      e.target.value = "";
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 animate-in fade-in duration-200">
      <div className="bg-white dark:bg-zinc-950 border border-zinc-200 dark:border-zinc-800 rounded-xl shadow-2xl w-full max-w-3xl max-h-[85vh] flex flex-col overflow-hidden">
        
        {/* Header */}
        <div className="flex items-center justify-between p-5 border-b border-zinc-200 dark:border-zinc-800 bg-zinc-50 dark:bg-zinc-900/50">
          <div>
            <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-100">Document Management</h2>
            <p className="text-sm text-zinc-500 mt-1">Manage files uploaded to the AI's knowledge base.</p>
          </div>
          <button 
            onClick={onClose}
            className="p-2 -mr-2 rounded-lg text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100 hover:bg-zinc-200 dark:hover:bg-zinc-800 transition-colors"
          >
            <X size={20} />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-5 space-y-6 bg-white dark:bg-zinc-950">
          
          {/* Upload Section */}
          <div className="border border-dashed border-zinc-300 dark:border-zinc-700 rounded-lg p-6 flex flex-col items-center justify-center bg-zinc-50 dark:bg-zinc-900/30 gap-4">
            <div className="flex flex-col gap-1 w-full max-w-sm">
              <label className="text-xs text-zinc-500 font-medium flex items-center gap-1"><Calendar size={14} /> Fecha del Documento (opcional)</label>
              <input 
                type="date" 
                value={documentDate} 
                onChange={e => setDocumentDate(e.target.value)} 
                className="p-2 text-sm border rounded text-zinc-800 dark:text-zinc-200 bg-white dark:bg-zinc-900" 
                disabled={isUploading} 
              />
            </div>
            <label className={`flex flex-col items-center cursor-pointer ${isUploading ? 'opacity-50 pointer-events-none' : ''}`}>
              <div className="w-12 h-12 bg-primary/10 text-primary rounded-full flex items-center justify-center mb-3">
                {isUploading ? <Loader2 className="animate-spin" size={24} /> : <Upload size={24} />}
              </div>
              <span className="text-sm font-medium text-zinc-900 dark:text-zinc-100">
                {isUploading ? 'Uploading...' : 'Click to select a file'}
              </span>
              <span className="text-xs text-zinc-500 mt-1">Supports PDF, DOCX, TXT, MD</span>
              <input 
                type="file" 
                className="hidden" 
                onChange={handleFileUpload}
                accept=".pdf,.docx,.txt,.md"
                disabled={isUploading}
              />
            </label>
            {uploadStatus && (
              <div className="mt-4 text-sm font-medium text-primary bg-primary/10 px-3 py-1.5 rounded-md animate-pulse">
                {uploadStatus}
              </div>
            )}
          </div>

          {/* Documents List */}
          <div>
            <div className="flex flex-col gap-3 mb-4">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-medium text-zinc-900 dark:text-zinc-100">Your Documents</h3>
                <button 
                  onClick={() => refetch()} 
                  className="text-xs flex items-center gap-1.5 text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100"
                >
                  <RefreshCw size={14} className={isLoading ? "animate-spin" : ""} />
                  Refresh
                </button>
              </div>
              <input
                type="text"
                placeholder="Buscar por ID o nombre de archivo..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full text-sm p-2 rounded border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 text-zinc-900 dark:text-zinc-100 placeholder:text-zinc-500"
              />
            </div>

            {isLoading ? (
              <div className="flex justify-center py-8">
                <Loader2 className="animate-spin text-zinc-400" size={24} />
              </div>
            ) : isError ? (
              <div className="text-center py-8 text-sm text-red-500 bg-red-50 dark:bg-red-950/20 rounded-lg">
                Error loading documents. Please try again.
              </div>
            ) : filteredDocuments.length === 0 ? (
              <div className="text-center py-12 border border-zinc-200 dark:border-zinc-800 rounded-lg bg-zinc-50/50 dark:bg-zinc-900/20">
                <File className="mx-auto text-zinc-400 mb-3" size={32} />
                <p className="text-sm text-zinc-500">No matching documents found.</p>
              </div>
            ) : (
              <div className="border border-zinc-200 dark:border-zinc-800 rounded-lg divide-y divide-zinc-200 dark:divide-zinc-800">
                {filteredDocuments.map((doc) => (
                  <div key={doc.doc_id} className="flex flex-col sm:flex-row sm:items-center justify-between p-4 gap-4 hover:bg-zinc-50 dark:hover:bg-zinc-900/50 transition-colors">
                    <div className="flex items-start gap-3 overflow-hidden">
                      <File className="shrink-0 text-zinc-400 mt-1" size={18} />
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-zinc-900 dark:text-zinc-100 truncate" title={doc.source_path}>
                          {doc.source_path.split(/[/\\]/).pop()}
                        </p>
                        <div className="flex items-center gap-3 mt-1.5 text-xs">
                          <span className={`px-2 py-0.5 rounded-full font-medium ${
                            doc.status === 'completed' ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400' :
                            doc.status === 'failed' ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400' :
                            'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400'
                          }`}>
                            {doc.status}
                          </span>
                          <span className="text-zinc-500">
                            {new Date(doc.created_at).toLocaleDateString()}
                          </span>
                        </div>
                      </div>
                    </div>
                    
                    <div className="flex items-center gap-2 shrink-0 sm:ml-4">
                      <button
                        onClick={async () => {
                          try {
                            const data = await getDocumentChunks(doc.doc_id);
                            setSelectedChunks(data.chunks || []);
                          } catch (e: any) { alert("Error: " + e.message); }
                        }}
                        className="p-1.5 text-zinc-500 hover:text-blue-600 hover:bg-blue-50 dark:hover:bg-blue-950/30 rounded-md transition-colors"
                        title="Ver Chunks"
                      >
                        <Eye size={16} />
                      </button>
                      <button
                        onClick={() => checkStatusMutation.mutate(doc.doc_id)}
                        disabled={checkStatusMutation.isPending}
                        className="p-1.5 text-zinc-500 hover:text-primary hover:bg-primary/10 rounded-md transition-colors"
                        title="Check Status"
                      >
                        <RefreshCw size={16} className={checkStatusMutation.isPending ? "animate-spin" : ""} />
                      </button>
                      <button
                        onClick={() => {
                          if (window.confirm("Are you sure you want to delete this document?")) {
                            deleteMutation.mutate(doc.doc_id);
                          }
                        }}
                        disabled={deleteMutation.isPending}
                        className="p-1.5 text-zinc-500 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-950/30 rounded-md transition-colors"
                        title="Delete Document"
                      >
                        {deleteMutation.isPending ? <Loader2 size={16} className="animate-spin" /> : <Trash2 size={16} />}
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {selectedChunks && (
          <div className="absolute inset-0 bg-white dark:bg-zinc-950 z-20 flex flex-col p-6 overflow-y-auto">
            <div className="flex justify-between items-center mb-4">
              <h3 className="text-lg font-semibold">Visualización de Chunks</h3>
              <button onClick={() => setSelectedChunks(null)} className="p-2 hover:bg-zinc-100 dark:hover:bg-zinc-800 rounded">
                <X size={20} />
              </button>
            </div>
            <div className="space-y-4">
              {Object.keys(selectedChunks).length === 0 || selectedChunks.length === 0 ? (
                <p className="text-zinc-500 text-sm">No hay chunks disponibles o no se han procesado aún.</p>
              ) : Array.isArray(selectedChunks) ? selectedChunks.map((c, i) => (
                <div key={i} className="p-4 border rounded text-sm bg-zinc-50 dark:bg-zinc-900 border-zinc-200 dark:border-zinc-800">
                  <div className="font-mono text-xs text-primary mb-2 break-all">{JSON.stringify(c.metadata)}</div>
                  <div>{c.page_content || c}</div>
                </div>
              )) : (
                <pre className="text-xs bg-zinc-100 dark:bg-zinc-900 p-4 rounded overflow-auto">{JSON.stringify(selectedChunks, null, 2)}</pre>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
