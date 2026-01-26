import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

interface DocumentRendererProps {
  data: any; // The JSON response from the backend
}

const DocumentRenderer: React.FC<DocumentRendererProps> = ({ data }) => {
  // Convert the JSON data to a markdown string
  const generateMarkdown = (data: any): string => {
    console.log("Generating markdown from data:", data);
    
    if (!data) return 'No data available';

    try {
      // If data is a string, try to parse it as JSON
      const parsedData = typeof data === 'string' ? JSON.parse(data) : data;
      
      let markdown = '# Project Analysis Report\n\n';

      // Add requirements section if available
      if (parsedData.requirements) {
        markdown += '## Project Requirements\n\n';
        
        if (parsedData.requirements.project_definition) {
          markdown += '### Project Definition\n\n';
          markdown += `${parsedData.requirements.project_definition}\n\n`;
        }
        
        if (parsedData.requirements.functional_requirements && parsedData.requirements.functional_requirements.length > 0) {
          markdown += '### Functional Requirements\n\n';
          parsedData.requirements.functional_requirements.forEach((req: any, index: number) => {
            markdown += `${index + 1}. ${req}\n`;
          });
          markdown += '\n';
        }
        
        if (parsedData.requirements.non_functional_requirements && parsedData.requirements.non_functional_requirements.length > 0) {
          markdown += '### Non-Functional Requirements\n\n';
          parsedData.requirements.non_functional_requirements.forEach((req: any, index: number) => {
            markdown += `${index + 1}. ${req}\n`;
          });
          markdown += '\n';
        }
      }

      // Add ambiguities section if available
      if (parsedData.ambiguities) {
        markdown += '## Potential Issues and Ambiguities\n\n';
        
        if (parsedData.ambiguities.questions && parsedData.ambiguities.questions.length > 0) {
          markdown += '### Key Questions\n\n';
          parsedData.ambiguities.questions.forEach((question: any, index: number) => {
            markdown += `${index + 1}. ${question}\n`;
          });
          markdown += '\n';
        }
        
        if (parsedData.ambiguities.risks && parsedData.ambiguities.risks.length > 0) {
          markdown += '### Potential Risks\n\n';
          parsedData.ambiguities.risks.forEach((risk: any, index: number) => {
            markdown += `${index + 1}. ${risk}\n`;
          });
          markdown += '\n';
        }
      }

      // Add tech stack recommendations if available
      if (parsedData.tech_stack) {
        markdown += '## Technical Recommendations\n\n';
        
        if (parsedData.tech_stack.primary_stack) {
          markdown += '### Recommended Technology Stack\n\n';
          Object.entries(parsedData.tech_stack.primary_stack).forEach(([category, techs]: [string, any]) => {
            markdown += `**${category}**: ${Array.isArray(techs) ? techs.join(', ') : techs}\n\n`;
          });
        }
        
        if (parsedData.tech_stack.alternatives) {
          markdown += '### Alternative Technologies\n\n';
          Object.entries(parsedData.tech_stack.alternatives).forEach(([category, techs]: [string, any]) => {
            markdown += `**${category}**: ${Array.isArray(techs) ? techs.join(', ') : techs}\n\n`;
          });
        }
      }

      return markdown;
    } catch (error) {
      console.error("Error generating markdown:", error);
      return `# Error Processing Document\n\nThere was an error processing the document data. Please try again.\n\nRaw data: ${JSON.stringify(data, null, 2)}`;
    }
  };

  const markdownContent = generateMarkdown(data);
  console.log("Generated markdown content:", markdownContent);

  return (
    <div className="document-renderer bg-white dark:bg-gray-800 rounded-lg p-6 shadow-md">
      <ReactMarkdown 
        remarkPlugins={[remarkGfm]} 
        className="prose dark:prose-invert max-w-none"
      >
        {markdownContent}
      </ReactMarkdown>
    </div>
  );
};

export default DocumentRenderer; 