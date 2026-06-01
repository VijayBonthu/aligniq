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
        """Issues assigned to the current user (flat rows). Uses /search/jql."""
        issues = self._search_jql(
            "assignee = currentUser() ORDER BY updated DESC",
            "key,summary,status,issuetype,labels,parent",
            50,
        )
        return [self._flatten_issue(i) for i in issues]

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
        
        # Search for issues with attachments (via /search/jql — /search was removed).
        issues = self._search_jql(jql, "attachment", 50)
        logger.info(f"attachment search returned {len(issues)} issues")

        # Prepare download directory
        download_dir = 'jira_attachments'
        os.makedirs(download_dir, exist_ok=True)

        # Track downloaded files
        downloaded_files = []

        # Process each issue
        for issue in issues:
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

    # ------------------------------------------------------------------
    # WRITE side — report -> Jira delivery handoff (epic + child stories).
    # ------------------------------------------------------------------
    def _cloud_base(self) -> str:
        cloud_id = self.resources[0]["id"]
        return f"https://api.atlassian.com/ex/jira/{cloud_id}/rest/api/3"

    def _browse_url(self, key: str) -> str:
        """Human-facing Jira URL for an issue/epic key, e.g. https://site.atlassian.net/browse/PROJ-1.
        Returned alongside keys so the UI can render clickable links, never a bare id."""
        site = (self.resources[0].get("url") or "").rstrip("/")
        return f"{site}/browse/{key}" if site and key else ""

    def _augment(self, data: dict) -> dict:
        """Attach browse_url to a Jira create/response dict when it carries a key."""
        if isinstance(data, dict) and data.get("key"):
            data["browse_url"] = self._browse_url(data["key"])
        return data

    def _raise_for(self, r, action: str):
        """Map a failed Jira response to the same HTTPException shapes the read paths use."""
        if r.status_code == 401:
            raise HTTPException(status_code=401, detail="Invalid Jira credentials")
        if r.status_code == 403:
            raise HTTPException(status_code=403, detail="Jira token lacks write permission (write:jira-work)")
        raise HTTPException(status_code=502, detail=f"Jira {action} failed ({r.status_code}): {r.text[:300]}")

    @staticmethod
    def _sanitize_labels(labels) -> list:
        """Jira labels cannot contain spaces — collapse whitespace to dashes and drop blanks."""
        out = []
        for l in labels or []:
            s = "-".join(str(l).split()).strip("-")
            if s:
                out.append(s)
        return out

    @staticmethod
    def _adf(text: str) -> dict:
        """Wrap plain text as a minimal Atlassian Document Format doc (Jira Cloud
        v3 requires ADF for description, not a raw string). Splits on blank lines
        into paragraphs; each capped to keep the payload sane."""
        paras = [p.strip() for p in (text or "").split("\n\n") if p.strip()] or [" "]
        return {
            "type": "doc",
            "version": 1,
            "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": p[:30000]}]}
                for p in paras
            ],
        }

    def get_projects(self) -> list:
        """List Jira projects the user can create issues in (key + name)."""
        base = self._cloud_base()
        r = requests.get(f"{base}/project/search", headers=self.headers, params={"maxResults": 50})
        if r.status_code == 200:
            return [
                {"key": p.get("key"), "name": p.get("name"), "id": p.get("id")}
                for p in r.json().get("values", [])
            ]
        if r.status_code == 401:
            raise HTTPException(status_code=401, detail="Invalid Jira credentials")
        raise HTTPException(status_code=502, detail=f"Jira project list failed ({r.status_code})")

    def create_issue(self, project_key: str, summary: str, description: str = "",
                     issue_type: str = "Task", parent_key: str = None, labels: list = None) -> dict:
        """Create one Jira issue. When `parent_key` is given we try to link to the
        epic; if Jira rejects it (company-managed projects link epics differently)
        we retry without the parent so the story is still created."""
        base = self._cloud_base()
        headers = {**self.headers, "Content-Type": "application/json"}
        fields = {
            "project": {"key": project_key},
            "summary": (summary or "Untitled")[:250],
            "description": self._adf(description),
            "issuetype": {"name": issue_type},
        }
        if labels:
            fields["labels"] = self._sanitize_labels(labels)
        if parent_key:
            fields["parent"] = {"key": parent_key}

        r = requests.post(f"{base}/issue", headers=headers, json={"fields": fields})
        if r.status_code in (200, 201):
            return self._augment(r.json())
        if parent_key and r.status_code == 400:
            fields.pop("parent", None)
            r = requests.post(f"{base}/issue", headers=headers, json={"fields": fields})
            if r.status_code in (200, 201):
                return self._augment(r.json())
        if r.status_code == 401:
            raise HTTPException(status_code=401, detail="Invalid Jira credentials")
        if r.status_code == 403:
            raise HTTPException(status_code=403, detail="Jira token lacks write permission (write:jira-work)")
        raise HTTPException(status_code=502, detail=f"Jira issue create failed ({r.status_code}): {r.text[:300]}")

    def create_epic(self, project_key: str, summary: str, description: str = "", labels: list = None) -> dict:
        """Create an Epic. Falls back to a Task if the project has no Epic type."""
        try:
            return self.create_issue(project_key, summary, description, issue_type="Epic", labels=labels)
        except HTTPException as e:
            if e.status_code == 502:  # project may not define an Epic issue type
                return self.create_issue(project_key, summary, description, issue_type="Task", labels=labels)
            raise

    # ------------------------------------------------------------------
    # Browse + update side — manage tickets already in Jira.
    # ------------------------------------------------------------------
    def _flatten_issue(self, issue: dict) -> dict:
        """Reduce a raw Jira issue to the flat shape the UI consumes."""
        f = issue.get("fields", {}) or {}
        status = (f.get("status") or {}).get("name")
        issuetype = (f.get("issuetype") or {}).get("name")
        parent = (f.get("parent") or {}).get("key")
        key = issue.get("key")
        return {
            "key": key,
            "summary": f.get("summary"),
            "status": status,
            "issue_type": issuetype,
            "labels": f.get("labels") or [],
            "parent_key": parent,
            "browse_url": self._browse_url(key),
        }

    def _search_jql(self, jql: str, fields: str, max_results: int = 50) -> list:
        """Run a JQL search via /search/jql. Atlassian REMOVED the old /search endpoint
        (it now returns 410 Gone), so all browsing goes through here. Returns the raw
        issues list (the response is {issues, nextPageToken, isLast})."""
        base = self._cloud_base()
        params = {"jql": jql, "fields": fields, "maxResults": max_results}
        r = requests.get(f"{base}/search/jql", headers=self.headers, params=params)
        if r.status_code == 200:
            return r.json().get("issues", [])
        self._raise_for(r, "issue search")

    def search_issues(self, project_key: str, jql_extra: str = None, max_results: int = 50) -> list:
        """Browse issues in a project (most-recently-updated first). Returns flat rows."""
        jql = f'project = "{project_key}"'
        if jql_extra:
            jql += f" {jql_extra}"
        jql += " ORDER BY updated DESC"
        issues = self._search_jql(jql, "key,summary,status,issuetype,labels,parent,updated", max_results)
        return [self._flatten_issue(i) for i in issues]

    def list_epics(self, project_key: str) -> list:
        """Epics in a project — the top level of the attach-target drill-down."""
        return self.search_issues(project_key, jql_extra="AND issuetype = Epic")

    def list_children(self, parent_key: str, max_results: int = 100) -> list:
        """Child issues (stories/tasks/sub-tasks) under an epic or story — for the
        epic -> children drill-down so users attach at the right level."""
        jql = f'parent = "{parent_key}" ORDER BY created ASC'
        issues = self._search_jql(jql, "key,summary,status,issuetype,labels,parent", max_results)
        return [self._flatten_issue(i) for i in issues]

    def update_issue(self, issue_key: str, summary: str = None, description: str = None) -> dict:
        """Edit an existing issue's summary and/or description. Only provided fields change."""
        base = self._cloud_base()
        headers = {**self.headers, "Content-Type": "application/json"}
        fields = {}
        if summary is not None:
            fields["summary"] = summary[:250]
        if description is not None:
            fields["description"] = self._adf(description)
        if not fields:
            raise HTTPException(status_code=400, detail="Nothing to update (summary or description required)")
        r = requests.put(f"{base}/issue/{issue_key}", headers=headers, json={"fields": fields})
        if r.status_code in (200, 204):
            return {"key": issue_key, "browse_url": self._browse_url(issue_key)}
        self._raise_for(r, "issue update")

    def set_labels(self, issue_key: str, add: list = None, remove: list = None) -> dict:
        """Add and/or remove labels (tags) on an issue via Jira's incremental label op."""
        ops = []
        for l in self._sanitize_labels(add):
            ops.append({"add": l})
        for l in self._sanitize_labels(remove):
            ops.append({"remove": l})
        if not ops:
            raise HTTPException(status_code=400, detail="No labels to add or remove")
        base = self._cloud_base()
        headers = {**self.headers, "Content-Type": "application/json"}
        r = requests.put(f"{base}/issue/{issue_key}", headers=headers, json={"update": {"labels": ops}})
        if r.status_code in (200, 204):
            return {"key": issue_key, "browse_url": self._browse_url(issue_key)}
        self._raise_for(r, "label update")

    @staticmethod
    def _adf_with_mentions(text: str, mentions=None) -> dict:
        """ADF doc: the comment text as paragraphs, plus a trailing 'cc:' line of @mentions
        so Jira notifies those users. `mentions` = [{account_id, display_name}]."""
        paras = [p.strip() for p in (text or "").split("\n\n") if p.strip()]
        content = [
            {"type": "paragraph", "content": [{"type": "text", "text": p[:30000]}]}
            for p in paras
        ] or [{"type": "paragraph", "content": [{"type": "text", "text": " "}]}]
        mlist = [m for m in (mentions or []) if m and m.get("account_id")]
        if mlist:
            cc = [{"type": "text", "text": "cc: "}]
            for i, m in enumerate(mlist):
                if i:
                    cc.append({"type": "text", "text": " "})
                name = m.get("display_name") or "user"
                cc.append({"type": "mention", "attrs": {"id": m["account_id"], "text": f"@{name}"}})
            content.append({"type": "paragraph", "content": cc})
        return {"type": "doc", "version": 1, "content": content}

    def add_comment(self, issue_key: str, body: str, mentions=None) -> dict:
        """Post a comment on an issue (ADF). `mentions` (list of {account_id, display_name})
        appends a trailing cc line that @-notifies those users."""
        base = self._cloud_base()
        headers = {**self.headers, "Content-Type": "application/json"}
        adf = self._adf_with_mentions(body, mentions) if mentions else self._adf(body)
        r = requests.post(f"{base}/issue/{issue_key}/comment", headers=headers, json={"body": adf})
        if r.status_code in (200, 201):
            data = r.json()
            return {"id": data.get("id"), "key": issue_key, "browse_url": self._browse_url(issue_key)}
        self._raise_for(r, "comment")

    def get_transitions(self, issue_key: str) -> list:
        """Available workflow transitions for an issue, e.g. To Do -> In Progress -> Done."""
        base = self._cloud_base()
        r = requests.get(f"{base}/issue/{issue_key}/transitions", headers=self.headers)
        if r.status_code == 200:
            return [
                {"id": t.get("id"), "name": t.get("name"), "to_status": (t.get("to") or {}).get("name")}
                for t in r.json().get("transitions", [])
            ]
        self._raise_for(r, "transitions list")

    def transition_issue(self, issue_key: str, transition_id: str) -> dict:
        """Move an issue across its workflow by transition id (from get_transitions)."""
        base = self._cloud_base()
        headers = {**self.headers, "Content-Type": "application/json"}
        r = requests.post(
            f"{base}/issue/{issue_key}/transitions",
            headers=headers,
            json={"transition": {"id": str(transition_id)}},
        )
        if r.status_code in (200, 204):
            return {"key": issue_key, "browse_url": self._browse_url(issue_key)}
        self._raise_for(r, "transition")

    # ------------------------------------------------------------------
    # People + attachments — assign/tag teammates and push the deliverable file.
    # ------------------------------------------------------------------
    def assign_issue(self, issue_key: str, account_id: str) -> dict:
        """Assign an issue to a Jira user by accountId."""
        base = self._cloud_base()
        headers = {**self.headers, "Content-Type": "application/json"}
        r = requests.put(f"{base}/issue/{issue_key}/assignee", headers=headers, json={"accountId": account_id})
        if r.status_code in (200, 204):
            return {"key": issue_key, "browse_url": self._browse_url(issue_key)}
        self._raise_for(r, "assign")

    def search_users(self, query: str = "", project_key: str = None, max_results: int = 20) -> list:
        """Users assignable in a project (for the tag/assign picker). Falls back to a general
        user search when no project is given. Returns flat {account_id, display_name, ...} rows."""
        base = self._cloud_base()
        if project_key:
            url = f"{base}/user/assignable/search"
            params = {"project": project_key, "query": query or "", "maxResults": max_results}
        else:
            url = f"{base}/user/search"
            params = {"query": query or "", "maxResults": max_results}
        r = requests.get(url, headers=self.headers, params=params)
        if r.status_code == 200:
            out = []
            for u in r.json() or []:
                if not u.get("accountId"):
                    continue
                avatars = u.get("avatarUrls") or {}
                out.append({
                    "account_id": u.get("accountId"),
                    "display_name": u.get("displayName"),
                    "email": u.get("emailAddress"),
                    "avatar_url": avatars.get("24x24") or avatars.get("48x48"),
                    "active": u.get("active", True),
                })
            return out
        self._raise_for(r, "user search")

    def add_attachment(self, issue_key: str, file_bytes: bytes, filename: str, content_type: str = None) -> dict:
        """Upload a file as an attachment on an issue. Jira requires the
        `X-Atlassian-Token: no-check` header and a multipart `file` field (we must NOT set
        Content-Type ourselves — requests sets the multipart boundary)."""
        base = self._cloud_base()
        headers = {**self.headers, "X-Atlassian-Token": "no-check"}
        files = {"file": (filename or "attachment", file_bytes, content_type or "application/octet-stream")}
        r = requests.post(f"{base}/issue/{issue_key}/attachments", headers=headers, files=files)
        if r.status_code in (200, 201):
            data = r.json()
            first = data[0] if isinstance(data, list) and data else {}
            return {
                "id": first.get("id"),
                "filename": first.get("filename", filename),
                "size": first.get("size"),
                "browse_url": self._browse_url(issue_key),
            }
        self._raise_for(r, "attachment upload")




