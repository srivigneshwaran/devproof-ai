import { useEffect, useState } from 'react'
import { listProjects, type Project } from '../api/projectsApi'

interface Props {
  selectedId: string | null
  onSelect: (id: string | null) => void
}

export function ProjectSelector({ selectedId, onSelect }: Props) {
  const [projects, setProjects] = useState<Project[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    listProjects()
      .then(setProjects)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-gray-500 text-sm py-4">
        <span className="h-4 w-4 rounded-full border-2 border-gray-300 border-t-blue-600 animate-spin" />
        Loading projects…
      </div>
    )
  }

  if (error) {
    return (
      <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-md px-3 py-2">
        Failed to load projects: {error}
      </p>
    )
  }

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
      {projects.map((project) => {
        const isSelected = selectedId === project.id
        return (
          <button
            key={project.id}
            type="button"
            onClick={() => onSelect(isSelected ? null : project.id)}
            className={`text-left rounded-lg border px-4 py-3 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 ${
              isSelected
                ? 'border-blue-600 bg-blue-50 ring-1 ring-blue-600'
                : 'border-gray-200 bg-white hover:border-blue-300 hover:bg-blue-50/40'
            }`}
          >
            <div className="flex items-center justify-between gap-2">
              <span className="font-medium text-gray-900 text-sm">{project.name}</span>
              <span className="shrink-0 text-xs text-gray-400">
                {project.file_count} file{project.file_count !== 1 ? 's' : ''}
              </span>
            </div>
            {project.description && (
              <p className="mt-1 text-xs text-gray-500 line-clamp-2">{project.description}</p>
            )}
          </button>
        )
      })}
    </div>
  )
}
