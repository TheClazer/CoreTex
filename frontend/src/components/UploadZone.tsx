import { useCallback, useState } from "react";
import { useDropzone, type FileRejection } from "react-dropzone";

const MAX_BYTES = 20 * 1024 * 1024;

interface Props {
  onFile: (file: File) => void;
  disabled?: boolean;
  selectedFile: File | null;
}

export function UploadZone({ onFile, disabled, selectedFile }: Props) {
  const [error, setError] = useState<string | null>(null);

  const handleDrop = useCallback(
    (accepted: File[], rejections: FileRejection[]) => {
      setError(null);
      if (rejections.length > 0) {
        const r = rejections[0];
        if (r.errors.some((e) => e.code === "file-too-large")) {
          setError("File is larger than 20 MB.");
        } else if (r.errors.some((e) => e.code === "file-invalid-type")) {
          setError("Only .docx files are accepted.");
        } else {
          setError("File rejected.");
        }
        return;
      }
      const file = accepted[0];
      if (!file) return;
      if (!file.name.toLowerCase().endsWith(".docx")) {
        setError("Only .docx files are accepted.");
        return;
      }
      if (file.size > MAX_BYTES) {
        setError("File is larger than 20 MB.");
        return;
      }
      onFile(file);
    },
    [onFile]
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop: handleDrop,
    accept: {
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [".docx"],
    },
    maxFiles: 1,
    maxSize: MAX_BYTES,
    disabled,
  });

  return (
    <div className="stack">
      <div
        {...getRootProps()}
        className={`dropzone ${isDragActive ? "active" : ""}`}
        role="button"
        aria-label="Upload a .docx file. Drag and drop or click to browse."
        tabIndex={0}
      >
        <input {...getInputProps()} aria-label="File input" />
        <div className="big">
          {isDragActive ? "Drop the .docx here" : "Drag & drop a .docx, or click to browse"}
        </div>
        <div className="small">Maximum 20 MB · Word documents only</div>
        {selectedFile && (
          <div className="file-name" aria-live="polite">
            {selectedFile.name} ({(selectedFile.size / 1024).toFixed(1)} KB)
          </div>
        )}
      </div>
      {error && (
        <div className="warning error" role="alert">
          {error}
        </div>
      )}
    </div>
  );
}
