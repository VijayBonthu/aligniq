import React from 'react';
import ProjectCard from './ProjectCard';
import NewProjectCard from './NewProjectCard';
import type { ProjectRow } from '../../types/overview';

interface Props {
  projects: ProjectRow[];
}

export default function ProjectsGrid({ projects }: Props) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3 md:gap-4">
      {projects.map(p => (
        <ProjectCard key={p.chat_history_id} project={p} />
      ))}
      <NewProjectCard />
    </div>
  );
}
