import requests
from fastapi import HTTPException
import os
from utils.logger import logger

class Integrations:
    def __init__(self, token: str):
        self.token = token
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json"
        }
        
        # Only one requests.get() call
        response = requests.get("https://api.atlassian.com/oauth/token/accessible-resources", headers=self.headers)

        if response.status_code == 200:
            self.resources = response.json()  # Parse JSON response
        elif response.status_code == 401:
            raise HTTPException(status_code=401, detail="Invalid details")
        else:
            raise HTTPException(status_code=500, detail="Internal server error")

    # def get_resources(self):
    #     return self.resources  
    
    def get_all_issues(self):

        try:
            user_resource_details = self.resources
            user_id = user_resource_details[0]["id"]
            jira_domain = self.resources[0]["url"]# Return parsed JSON instead of raw response
            JIRA_API_URL = f"https://api.atlassian.com/ex/jira/{user_id}/rest/api/3/search"   
            headers = self.headers
            params = {
                "jql": "assignee=currentUser()",
                "fields": "key,summary,description,attachment"
            }

            response  = requests.get(JIRA_API_URL, headers=headers, params=params)
            
            if response.status_code == 200:
                return response.json()  # Parse JSON response
            elif response.status_code == 401:
                raise HTTPException(status_code=401, detail="Invalid details")
            else:
                raise HTTPException(status_code=500, detail="Internal server error")
        except HTTPException as e:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Internal server error: {e}")

    def download_jira_attachments(self, issue_key=None, attachment_id=None, download_file_name=None):

        """
        Download attachments for Jira issues
        
        :param access_token: Jira OAuth access token
        :param cloud_id: Atlassian Cloud ID
        :param issue_key: Specific issue key (optional)
        :return: List of downloaded files
        """
        # Prepare headers for API request
        headers = self.headers

        cloud_id  = self.resources[0]["id"]
        
        # Base URLs
        base_url = f'https://api.atlassian.com/ex/jira/{cloud_id}/rest/api/3'
    
        # Prepare JQL query
        jql = 'attachments IS NOT EMPTY'
        if issue_key:
            jql = f'issue = {issue_key}'
        
        # Search for issues with attachments
        search_params = {
            'jql': jql,
            'fields': ['attachment'],
            'maxResults': 50
        }
        
        # Perform search request
        search_response = requests.get(
            f'{base_url}/search', 
            headers=headers, 
            params=search_params
        )
        search_response.raise_for_status()

        logger.info(f"search_response: {search_response.json()}")

        
        # Prepare download directory
        download_dir = 'jira_attachments'
        os.makedirs(download_dir, exist_ok=True)
        
        # Track downloaded files
        downloaded_files = []
        
        # Process each issue
        for issue in search_response.json()['issues']:
            # Create issue-specific directory
            issue_dir = os.path.join(download_dir, issue['key'])
            os.makedirs(issue_dir, exist_ok=True)
            
            # Get attachments for this issue
            attachments = issue['fields'].get('attachment', [])

            if attachment_id:
                attachments= [a for a in attachments if str(a['id']) == str(attachment_id)]
        
            if download_file_name:
                    attachments= [a for a in attachments if a['filename'] == str(download_file_name)]
            
            # Validate attachments
            if not attachments:
                print(f"No matching attachments found for issue {issue_key}")
                return None

            
            
            # Download each attachment
            for attachment in attachments:
                try:
                    # Prepare download
                    filename =attachment['id']+ "_" + attachment['filename']
                    file_path = os.path.join(issue_dir, filename)
                    
                    # Download file
                    file_response = requests.get(
                        attachment['content'], 
                        headers=headers,
                        stream=True
                    )
                    file_response.raise_for_status()
                    
                    # Save file
                    with open(file_path, 'wb') as f:
                        for chunk in file_response.iter_content(chunk_size=8192):
                            f.write(chunk)
                    
                    # Track downloaded file
                    downloaded_files.append({
                        'issue_key': issue['key'],
                        'filename': filename,
                        'local_path': file_path,
                        'attachment_id': attachment['id']
                    })
                    
                    print(f"Downloaded: {issue['key']} - {filename}")
                
                except Exception as e:
                    print(f"Error downloading {filename}: {e}")
        
        return downloaded_files
    
    def get_single_issues_(self, issue_key:str):

        try:
            user_resource_details = self.resources
            user_id = user_resource_details[0]["id"]
            jira_domain = self.resources[0]["url"]# Return parsed JSON instead of raw response
            JIRA_API_URL = f"https://api.atlassian.com/ex/jira/{user_id}/rest/api/3"   
            headers = self.headers

            logger.info(f"inside get single issues: {JIRA_API_URL, issue_key}")

            if issue_key:
                jql = f'issue={issue_key}'

            search_params = {
            'jql': jql,
            "fields": "key,summary,description,attachment, comment, status",
            'maxResults': 50
        }

            response  = requests.get(f"{JIRA_API_URL}/issue/{issue_key}", headers=headers, params=search_params)
            logger.info(f"response inside get single issues: {response.json()}")
            
            if response.status_code == 200:
                return response.json()  # Parse JSON response
            elif response.status_code == 401:
                raise HTTPException(status_code=401, detail="Invalid details")
            else:
                raise HTTPException(status_code=500, detail="Internal server error")
        except HTTPException as e:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Internal server error: {e}")




